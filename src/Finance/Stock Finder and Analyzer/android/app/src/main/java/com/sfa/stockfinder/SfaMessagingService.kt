package com.sfa.stockfinder

import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

/**
 * Receives the computer's messages. They are data-only with high priority, so this runs
 * whether the app is open or not; the notification is built here (own channels and tap
 * action) and every message is kept in the in-app history.
 */
class SfaMessagingService : FirebaseMessagingService() {

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        if (data.isEmpty()) return
        val store = Store(this)
        // any message proves the computer is alive
        store.lastHeartbeat = System.currentTimeMillis()
        if (data["type"] == "heartbeat") {
            data["every_hours"]?.toIntOrNull()?.let { store.heartbeatEveryHours = it }
            if (store.dashboardUrl.isBlank()) data["url"]?.let { store.dashboardUrl = it }
            return
        }
        val alert = Alert.fromData(data)
        store.add(alert)
        if (!store.isMuted(alert.type)) Notifier.show(this, alert)
    }

    override fun onNewToken(token: String) {
        // a new registration loses topic subscriptions: subscribe again
        val topic = Store(this).topic
        if (topic.isNotBlank()) FirebaseMessaging.getInstance().subscribeToTopic(topic)
    }
}
