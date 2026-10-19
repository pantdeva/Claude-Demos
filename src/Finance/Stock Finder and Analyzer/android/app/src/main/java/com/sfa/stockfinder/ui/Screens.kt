package com.sfa.stockfinder.ui

import android.annotation.SuppressLint
import android.content.Intent
import android.provider.Settings
import android.text.format.DateUtils
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.runtime.rememberCoroutineScope
import com.sfa.stockfinder.Account
import com.sfa.stockfinder.Alert
import com.sfa.stockfinder.MainActivity
import com.sfa.stockfinder.Notifier
import com.sfa.stockfinder.Store
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.util.concurrent.TimeUnit

@Composable
fun SfaTheme(content: @Composable () -> Unit) {
    val blue = Color(0xFF2457C5)
    val scheme = if (isSystemInDarkTheme()) darkColorScheme(primary = Color(0xFF7AA2FF)) else lightColorScheme(primary = blue)
    MaterialTheme(colorScheme = scheme, content = content)
}

@Composable
fun AppScreen(activity: MainActivity) {
    val store = remember { Store(activity) }
    var tab by remember { mutableIntStateOf(0) }
    var dashboardTarget by remember { mutableStateOf(store.dashboardUrl) }
    val snack = remember { SnackbarHostState() }

    // a tapped notification opens its page on the Dashboard tab
    val pending = activity.pendingLink.value
    LaunchedEffect(pending) {
        if (pending != null) {
            dashboardTarget = pending
            tab = 1
            activity.pendingLink.value = null
        }
    }
    val msg = activity.message.value
    LaunchedEffect(msg) {
        if (msg != null) {
            snack.showSnackbar(msg)
            activity.message.value = null
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snack) },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(selected = tab == 0, onClick = { tab = 0 },
                    icon = { Icon(Icons.Filled.Notifications, null) }, label = { Text("Alerts") })
                NavigationBarItem(selected = tab == 1, onClick = { dashboardTarget = store.dashboardUrl; tab = 1 },
                    icon = { Icon(Icons.Filled.Home, null) }, label = { Text("Dashboard") })
                NavigationBarItem(selected = tab == 2, onClick = { tab = 2 },
                    icon = { Icon(Icons.Filled.Settings, null) }, label = { Text("Settings") })
            }
        },
    ) { pad ->
        Box(Modifier.padding(pad).fillMaxSize()) {
            when (tab) {
                0 -> AlertsScreen(store) { a -> dashboardTarget = store.link(a.path, a.url); tab = 1 }
                1 -> DashboardScreen(dashboardTarget)
                else -> SettingsScreen(activity, store) { activity.message.value = it }
            }
        }
    }
}

private fun ago(ms: Long): String =
    if (ms <= 0) "never" else DateUtils.getRelativeTimeSpanString(ms, System.currentTimeMillis(), DateUtils.MINUTE_IN_MILLIS).toString()

private val typeLabel = mapOf("lead" to "Lead", "ipo" to "IPO", "valuation" to "Valuation", "digest" to "Digest",
    "alert" to "Alert", "test" to "Test")

@Composable
fun AlertsScreen(store: Store, open: (Alert) -> Unit) {
    var alerts by remember { mutableStateOf(store.alerts()) }
    var hb by remember { mutableStateOf(store.lastHeartbeat) }
    LaunchedEffect(Unit) {                       // pick up messages that arrive while the screen is open
        while (true) {
            alerts = store.alerts()
            hb = store.lastHeartbeat
            delay(5_000)
        }
    }
    val stale = hb > 0 && System.currentTimeMillis() - hb > TimeUnit.HOURS.toMillis(2L * store.heartbeatEveryHours)
    val linked = Account.user != null || store.topic.isNotBlank()
    Column(Modifier.fillMaxSize()) {
        Card(
            Modifier.fillMaxWidth().padding(12.dp),
            colors = CardDefaults.cardColors(
                containerColor = if (!linked || stale) MaterialTheme.colorScheme.errorContainer
                else MaterialTheme.colorScheme.secondaryContainer,
            ),
        ) {
            Column(Modifier.padding(14.dp)) {
                Text(
                    when {
                        !linked -> "Not signed in"
                        stale -> "Computer quiet since ${ago(hb)}"
                        hb == 0L -> "Signed in · waiting for the computer's first message"
                        else -> "Signed in · computer last heard from ${ago(hb)}"
                    },
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    if (!linked) "Open Settings and sign in with the Google account listed in the computer's SFA_NOTIFY_EMAILS."
                    else "${alerts.size} alerts kept on this phone.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
        if (alerts.isEmpty()) {
            Text("No alerts yet.", Modifier.padding(16.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        LazyColumn(Modifier.fillMaxSize()) {
            items(alerts, key = { it.id }) { a ->
                Column(
                    Modifier.fillMaxWidth().clickable(enabled = a.path.isNotBlank()) { open(a) }
                        .padding(horizontal = 16.dp, vertical = 10.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        AssistChip(onClick = { open(a) }, label = { Text(typeLabel[a.type] ?: a.type) })
                        Spacer(Modifier.padding(4.dp))
                        Text(ago(a.receivedAt), style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Text(a.title, fontWeight = FontWeight.SemiBold)
                    if (a.body.isNotBlank()) Text(a.body, style = MaterialTheme.typography.bodyMedium)
                }
                HorizontalDivider()
            }
        }
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun DashboardScreen(target: String) {
    if (target.isBlank()) {
        Text("Set the dashboard address in Settings (for example your computer's Tailscale name with :8000).",
            Modifier.padding(16.dp))
        return
    }
    var error by remember { mutableStateOf<String?>(null) }
    var web by remember { mutableStateOf<WebView?>(null) }
    var canBack by remember { mutableStateOf(false) }
    var loaded by remember { mutableStateOf("") }            // last address we were asked to open
    BackHandler(enabled = canBack) { web?.goBack() }
    Box(Modifier.fillMaxSize()) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { ctx ->
                WebView(ctx).apply {
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    webViewClient = object : WebViewClient() {
                        override fun onReceivedError(view: WebView, req: WebResourceRequest, err: WebResourceError) {
                            if (req.isForMainFrame) error = "Can't reach the dashboard at $target (${err.description}). " +
                                "Is the computer on, and is this phone on the same Wi-Fi or Tailscale network?"
                        }

                        override fun onPageFinished(view: WebView, url: String?) {
                            canBack = view.canGoBack()
                        }
                    }
                    web = this
                    loaded = target
                    loadUrl(target)
                }
            },
            // only a new target reloads; browsing inside the dashboard is left alone
            update = { v -> if (loaded != target) { loaded = target; error = null; v.loadUrl(target) } },
        )
        error?.let { e ->
            Card(Modifier.align(Alignment.BottomCenter).padding(12.dp).fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text(e)
                    TextButton(onClick = { error = null; web?.reload() }) { Text("Retry") }
                }
            }
        }
    }
}

@Composable
fun SettingsScreen(activity: MainActivity, store: Store, say: (String) -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var email by remember { mutableStateOf(Account.user?.email) }
    var busy by remember { mutableStateOf(false) }
    var url by remember { mutableStateOf(store.dashboardUrl) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Account", style = MaterialTheme.typography.titleMedium)
        if (email == null) {
            Text("Sign in with the Google account you listed in SFA_NOTIFY_EMAILS on the computer. Only that " +
                "account's phones receive notifications.", style = MaterialTheme.typography.bodySmall)
            Button(enabled = !busy, onClick = {
                busy = true
                scope.launch {
                    try {
                        email = Account.signIn(activity).email
                        say("Signed in as $email. Use “Send test notification” on the dashboard's Service page to check.")
                    } catch (e: Exception) {
                        say(e.message ?: "Sign-in failed.")
                    } finally {
                        busy = false
                    }
                }
            }) { Text(if (busy) "Signing in…" else "Sign in with Google") }
        } else {
            Text("Signed in as $email", fontWeight = FontWeight.SemiBold)
            Text("This phone is registered to receive the computer's notifications. Registered " +
                "${ago(store.lastRegistered)}.", style = MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(enabled = !busy, onClick = {
                    busy = true
                    scope.launch {
                        val r = runCatching { Account.register(ctx) }
                        say(if (r.isSuccess) "Registration refreshed." else "Could not register: ${r.exceptionOrNull()?.message}")
                        busy = false
                    }
                }) { Text("Re-register") }
                OutlinedButton(enabled = !busy, onClick = {
                    busy = true
                    scope.launch {
                        Account.signOut(ctx)
                        email = null
                        busy = false
                        say("Signed out: this phone no longer receives notifications.")
                    }
                }) { Text("Sign out") }
            }
        }

        Spacer(Modifier.height(8.dp))
        Text("Dashboard", style = MaterialTheme.typography.titleMedium)
        Text("The address the Dashboard tab opens. Opening the set-up link from the dashboard's Service page on " +
            "this phone fills it in.", style = MaterialTheme.typography.bodySmall)
        OutlinedTextField(url, { url = it }, Modifier.fillMaxWidth(), label = { Text("Dashboard address") },
            placeholder = { Text("http://my-pc.tailnet-name.ts.net:8000") }, singleLine = true)
        Button(onClick = {
            val u = url.trim()
            if (u.isNotBlank() && !u.startsWith("http://") && !u.startsWith("https://")) say("The address starts with http:// or https://")
            else { store.dashboardUrl = u; say("Saved.") }
        }) { Text("Save address") }

        Spacer(Modifier.height(8.dp))
        Text("Notify me about", style = MaterialTheme.typography.titleMedium)
        Store.TYPES.forEach { t ->
            var on by remember { mutableStateOf(!store.isMuted(t)) }
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(mapOf("lead" to "Top leads", "ipo" to "IPO pipeline", "valuation" to "Valuation changes",
                    "digest" to "Daily digest", "alert" to "Service alerts")[t] ?: t, Modifier.weight(1f))
                Switch(on, { on = it; store.setMuted(t, !it) })
            }
        }
        Text("Muted types are still kept in the Alerts list. Sound and vibration per type: Android settings → Apps → " +
            "SFA Notifier → Notifications.", style = MaterialTheme.typography.bodySmall)

        Spacer(Modifier.height(8.dp))
        Text("Check and tune", style = MaterialTheme.typography.titleMedium)
        OutlinedButton(onClick = {
            val a = Alert("local-${System.currentTimeMillis()}", "test", "Test notification (from this phone)",
                "This one was made on the phone. Use “Send test notification” on the dashboard to test the full path.",
                "", "#service", "", "", System.currentTimeMillis())
            store.add(a)
            Notifier.show(ctx, a)
        }) { Text("Show a test notification") }
        OutlinedButton(onClick = {
            ctx.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }) { Text("Battery optimisation settings") }
        Text("If alerts arrive late, set SFA Notifier to “Unrestricted” / “Not optimised” there.",
            style = MaterialTheme.typography.bodySmall)
        OutlinedButton(onClick = { store.clearAlerts(); say("Alert history cleared.") }) { Text("Clear alert history") }
    }
}
