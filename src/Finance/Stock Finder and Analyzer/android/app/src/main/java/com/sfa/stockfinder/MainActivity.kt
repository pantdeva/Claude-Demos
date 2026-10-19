package com.sfa.stockfinder

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.mutableStateOf
import androidx.core.content.ContextCompat
import com.google.firebase.messaging.FirebaseMessaging
import com.sfa.stockfinder.ui.AppScreen
import com.sfa.stockfinder.ui.SfaTheme

class MainActivity : ComponentActivity() {

    /** Dashboard address to open (set by a tapped notification). */
    val pendingLink = mutableStateOf<String?>(null)

    /** One-off message for the snackbar (pairing result etc.). */
    val message = mutableStateOf<String?>(null)

    private val askPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (!granted) message.value = "Notifications are off for this app: alerts will only appear inside it."
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handle(intent)
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            askPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        setContent { SfaTheme { AppScreen(this) } }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handle(intent)
    }

    private fun handle(intent: Intent?) {
        intent ?: return
        val store = Store(this)
        val data = intent.data
        if (data != null && data.scheme == "sfa" && data.host == "pair") {
            val topic = data.getQueryParameter("topic").orEmpty()
            val url = data.getQueryParameter("url").orEmpty()
            if (topic.isBlank()) {
                message.value = "That pairing link has no code."
            } else {
                pair(store, topic, url) { ok, msg -> message.value = msg; if (ok) pendingLink.value = null }
            }
            return
        }
        val path = intent.getStringExtra(EXTRA_PATH)
        if (path != null) pendingLink.value = store.link(path, intent.getStringExtra(EXTRA_URL).orEmpty())
    }

    companion object {
        const val EXTRA_PATH = "path"
        const val EXTRA_URL = "url"

        /** Subscribe to the computer's topic (the pairing code) and remember the dashboard address. */
        fun pair(store: Store, topic: String, url: String, done: (Boolean, String) -> Unit) {
            val fm = FirebaseMessaging.getInstance()
            val old = store.topic
            if (old.isNotBlank() && old != topic) fm.unsubscribeFromTopic(old)
            store.topic = topic
            if (url.isNotBlank()) store.dashboardUrl = url
            fm.subscribeToTopic(topic).addOnCompleteListener { t ->
                if (t.isSuccessful) done(true, "Paired. Use “Send test notification” on the dashboard’s Service page to check.")
                else done(false, "Could not subscribe: ${t.exception?.message ?: "no network?"}")
            }
        }
    }
}
