package com.sfa.stockfinder

import android.app.Activity
import android.content.Context
import android.os.Build
import androidx.credentials.ClearCredentialStateRequest
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import androidx.credentials.exceptions.NoCredentialException
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseUser
import com.google.firebase.auth.GoogleAuthProvider
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.SetOptions
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import java.util.UUID

/**
 * Google sign-in (Credential Manager → Firebase Authentication) and the device registry.
 *
 * When signed in, this phone writes its FCM registration token to Firestore at
 *   users/{uid}                 { email, updatedAt }
 *   users/{uid}/devices/{id}    { token, model, app, updatedAt }
 * The security rules (firestore.rules) let only that signed-in user read or write there.
 * The computer reads the registry with its service-account key and sends only to the
 * devices of accounts listed in its SFA_NOTIFY_EMAILS setting.
 */
object Account {
    private val auth get() = FirebaseAuth.getInstance()
    private val db get() = FirebaseFirestore.getInstance()
    private val background = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    val user: FirebaseUser? get() = auth.currentUser

    /** Shows the Google account picker, then signs in to Firebase with the chosen account. */
    suspend fun signIn(activity: Activity): FirebaseUser {
        val option = GetSignInWithGoogleOption.Builder(activity.getString(R.string.default_web_client_id)).build()
        val request = GetCredentialRequest.Builder().addCredentialOption(option).build()
        val result = try {
            CredentialManager.create(activity).getCredential(activity, request)
        } catch (e: GetCredentialCancellationException) {
            throw SignInError("Sign-in cancelled.")
        } catch (e: NoCredentialException) {
            throw SignInError("No Google account on this phone: add one in Android Settings → Accounts.")
        } catch (e: GetCredentialException) {
            throw SignInError(explain(e))
        }
        val cred = result.credential
        if (cred !is CustomCredential || cred.type != GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) {
            throw SignInError("Unexpected credential type: ${cred.type}")
        }
        val idToken = GoogleIdTokenCredential.createFrom(cred.data).idToken
        val user = auth.signInWithCredential(GoogleAuthProvider.getCredential(idToken, null)).await().user
            ?: throw SignInError("Firebase did not return a user.")
        register(activity)
        return user
    }

    /** Removes this phone from the registry, then signs out (the computer stops sending here). */
    suspend fun signOut(context: Context) {
        val u = user
        if (u != null) {
            runCatching { devices(u.uid).document(deviceId(context)).delete().await() }
        }
        auth.signOut()
        runCatching { CredentialManager.create(context).clearCredentialState(ClearCredentialStateRequest()) }
    }

    /** Writes (or refreshes) this phone's FCM token in the registry. No-op when signed out. */
    suspend fun register(context: Context, token: String? = null) {
        val u = user ?: return
        val t = token ?: FirebaseMessaging.getInstance().token.await()
        db.collection("users").document(u.uid)
            .set(mapOf("email" to (u.email ?: ""), "updatedAt" to FieldValue.serverTimestamp()), SetOptions.merge())
            .await()
        val version = runCatching {
            context.packageManager.getPackageInfo(context.packageName, 0).versionName
        }.getOrNull() ?: ""
        devices(u.uid).document(deviceId(context)).set(
            mapOf(
                "token" to t,
                "model" to "${Build.MANUFACTURER} ${Build.MODEL}",
                "app" to version,
                "updatedAt" to FieldValue.serverTimestamp(),
            ),
        ).await()
        Store(context).lastRegistered = System.currentTimeMillis()
    }

    /** Fire-and-forget registration, for the app start and token refreshes. */
    fun registerInBackground(context: Context, token: String? = null) {
        if (user == null) return
        val app = context.applicationContext
        background.launch { runCatching { register(app, token) } }
    }

    private fun devices(uid: String) = db.collection("users").document(uid).collection("devices")

    /** Random id kept for the life of the installation, so re-registering updates one document. */
    fun deviceId(context: Context): String {
        val store = Store(context)
        return store.deviceId.ifBlank { UUID.randomUUID().toString().also { store.deviceId = it } }
    }

    private fun explain(e: GetCredentialException): String {
        val m = e.message.orEmpty()
        return when {
            "10" in m || "DEVELOPER_ERROR" in m ->
                "Google sign-in is not set up for this build (code 10): add this computer's SHA-1 fingerprint " +
                    "to the Android app in Firebase and download google-services.json again (ANDROID.md, step 4)."
            else -> "Sign-in failed: ${e.type} ${m.take(160)}"
        }
    }

    class SignInError(msg: String) : Exception(msg)
}
