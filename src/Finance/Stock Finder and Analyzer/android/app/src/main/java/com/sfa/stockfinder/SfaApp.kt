package com.sfa.stockfinder

import android.app.Application
import com.google.firebase.messaging.FirebaseMessaging

class SfaApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Notifier.createChannels(this)
        HeartbeatWorker.schedule(this)
        val topic = Store(this).topic
        if (topic.isNotBlank()) FirebaseMessaging.getInstance().subscribeToTopic(topic)
    }
}
