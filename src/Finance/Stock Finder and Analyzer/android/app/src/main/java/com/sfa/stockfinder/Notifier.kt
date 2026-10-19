package com.sfa.stockfinder

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat

/** Notification channels (one per event type, so each can be tuned in Android settings) and display. */
object Notifier {
    private data class Ch(val id: String, val name: String, val importance: Int, val desc: String)

    private val channels = listOf(
        Ch("leads", "Top leads", NotificationManager.IMPORTANCE_HIGH, "A company enters the top leads or its score jumps"),
        Ch("ipo", "IPO pipeline", NotificationManager.IMPORTANCE_HIGH, "New IPO names and stage changes"),
        Ch("valuation", "Valuations", NotificationManager.IMPORTANCE_DEFAULT, "Verdict changes and big fair-value moves"),
        Ch("digest", "Daily digest", NotificationManager.IMPORTANCE_DEFAULT, "Morning summary"),
        Ch("alerts", "Service alerts", NotificationManager.IMPORTANCE_HIGH, "Failed jobs, stale data, computer gone quiet"),
    )

    fun createChannels(context: Context) {
        val nm = context.getSystemService(NotificationManager::class.java)
        channels.forEach { c ->
            nm.createNotificationChannel(NotificationChannel(c.id, c.name, c.importance).apply { description = c.desc })
        }
    }

    fun channelFor(type: String) = when (type) {
        "lead" -> "leads"
        "ipo" -> "ipo"
        "valuation" -> "valuation"
        "digest" -> "digest"
        else -> "alerts"
    }

    fun show(context: Context, a: Alert) {
        val nm = NotificationManagerCompat.from(context)
        if (!nm.areNotificationsEnabled()) return
        val open = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra(MainActivity.EXTRA_PATH, a.path)
            putExtra(MainActivity.EXTRA_URL, a.url)
        }
        val pi = PendingIntent.getActivity(
            context, a.id.hashCode(), open, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val n = NotificationCompat.Builder(context, channelFor(a.type))
            .setSmallIcon(R.drawable.ic_stat_sfa)
            .setContentTitle(a.title)
            .setContentText(a.body.lineSequence().firstOrNull() ?: "")
            .setStyle(NotificationCompat.BigTextStyle().bigText(a.body))
            .setContentIntent(pi)
            .setAutoCancel(true)
            .setGroup(a.type)
            .build()
        try {
            nm.notify(a.id.hashCode(), n)
        } catch (_: SecurityException) {
            // notification permission revoked: the alert is still kept in the in-app history
        }
    }
}
