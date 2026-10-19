package com.sfa.stockfinder

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

/**
 * Watchdog: the computer sends a silent heartbeat every few hours. If nothing has
 * arrived for twice that long, the computer is probably off, asleep or offline, so the
 * phone raises a local alert (at most once per quiet spell).
 */
class HeartbeatWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val store = Store(applicationContext)
        if (store.topic.isBlank() || store.lastHeartbeat == 0L) return Result.success()
        val limit = TimeUnit.HOURS.toMillis(2L * store.heartbeatEveryHours)
        val now = System.currentTimeMillis()
        val quietFor = now - store.lastHeartbeat
        if (quietFor > limit && store.quietWarnedAt < store.lastHeartbeat) {
            store.quietWarnedAt = now
            val hours = TimeUnit.MILLISECONDS.toHours(quietFor)
            val alert = Alert(
                id = "quiet-$now", type = "alert", title = "Stock Finder computer has gone quiet",
                body = "No message for $hours h. The computer may be off, asleep or offline, or the service stopped.",
                symbol = "", path = "#service", url = "", sent = "", receivedAt = now,
            )
            store.add(alert)
            Notifier.show(applicationContext, alert)
        }
        return Result.success()
    }

    companion object {
        fun schedule(context: Context) {
            val req = PeriodicWorkRequestBuilder<HeartbeatWorker>(3, TimeUnit.HOURS).build()
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork("sfa-heartbeat", ExistingPeriodicWorkPolicy.KEEP, req)
        }
    }
}
