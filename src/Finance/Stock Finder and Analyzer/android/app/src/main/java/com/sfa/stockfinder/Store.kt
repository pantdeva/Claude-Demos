package com.sfa.stockfinder

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** One notification received from the computer (see sfa/notify/__init__.py for the contract). */
data class Alert(
    val id: String,
    val type: String,
    val title: String,
    val body: String,
    val symbol: String,
    val path: String,
    val url: String,
    val sent: String,
    val receivedAt: Long,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("id", id).put("type", type).put("title", title).put("body", body)
        .put("symbol", symbol).put("path", path).put("url", url).put("sent", sent).put("receivedAt", receivedAt)

    companion object {
        fun fromJson(o: JSONObject) = Alert(
            o.optString("id"), o.optString("type"), o.optString("title"), o.optString("body"),
            o.optString("symbol"), o.optString("path"), o.optString("url"), o.optString("sent"),
            o.optLong("receivedAt"),
        )

        fun fromData(d: Map<String, String>) = Alert(
            d["id"] ?: System.currentTimeMillis().toString(), d["type"] ?: "alert", d["title"] ?: "Stock Finder",
            d["body"] ?: "", d["symbol"] ?: "", d["path"] ?: "", d["url"] ?: "", d["sent"] ?: "",
            System.currentTimeMillis(),
        )
    }
}

/** Small key-value store (SharedPreferences): settings, alert history, heartbeat, device id. */
class Store(context: Context) {
    private val p = context.applicationContext.getSharedPreferences("sfa", Context.MODE_PRIVATE)

    /** Random id of this installation in the Firestore device registry. */
    var deviceId: String
        get() = p.getString("device_id", "") ?: ""
        set(v) = p.edit().putString("device_id", v).apply()

    var lastRegistered: Long
        get() = p.getLong("registered", 0L)
        set(v) = p.edit().putLong("registered", v).apply()

    /** Only for computers set to `audience: topic` (the older shared-code mode). */
    var topic: String
        get() = p.getString("topic", "") ?: ""
        set(v) = p.edit().putString("topic", v.trim()).apply()

    var dashboardUrl: String
        get() = p.getString("url", "") ?: ""
        set(v) = p.edit().putString("url", v.trim().trimEnd('/')).apply()

    var lastHeartbeat: Long
        get() = p.getLong("hb", 0L)
        set(v) = p.edit().putLong("hb", v).apply()

    var heartbeatEveryHours: Int
        get() = p.getInt("hb_every", 6)
        set(v) = p.edit().putInt("hb_every", v).apply()

    var quietWarnedAt: Long
        get() = p.getLong("quiet_warned", 0L)
        set(v) = p.edit().putLong("quiet_warned", v).apply()

    fun isMuted(type: String) = p.getBoolean("mute_$type", false)
    fun setMuted(type: String, muted: Boolean) = p.edit().putBoolean("mute_$type", muted).apply()

    fun alerts(): List<Alert> {
        val arr = JSONArray(p.getString("alerts", "[]"))
        return (0 until arr.length()).map { Alert.fromJson(arr.getJSONObject(it)) }
    }

    @Synchronized
    fun add(a: Alert) {
        val list = (listOf(a) + alerts().filter { it.id != a.id }).take(MAX_ALERTS)
        val arr = JSONArray()
        list.forEach { arr.put(it.toJson()) }
        p.edit().putString("alerts", arr.toString()).apply()
    }

    fun clearAlerts() = p.edit().putString("alerts", "[]").apply()

    /** Full dashboard address for a route like "#company/TSM". */
    fun link(path: String, url: String = ""): String {
        val base = (url.ifBlank { dashboardUrl }).trimEnd('/')
        return if (path.isBlank()) base else "$base/$path"
    }

    companion object {
        const val MAX_ALERTS = 200
        val TYPES = listOf("lead", "ipo", "valuation", "digest", "alert")
    }
}
