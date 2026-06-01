package com.naveenhospital.medtrack.core.data.notification

import com.naveenhospital.medtrack.core.domain.model.NotificationPayload
import com.naveenhospital.medtrack.core.domain.model.VitalsTriggerMetric
import com.squareup.moshi.JsonAdapter
import com.squareup.moshi.Moshi
import com.squareup.moshi.Types
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import org.json.JSONArray
import org.json.JSONObject

private val payloadJsonAdapter: JsonAdapter<Map<String, Any?>> =
    Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()
        .adapter(Types.newParameterizedType(Map::class.java, String::class.java, Any::class.java))

internal fun notificationPayloadToJson(payload: Map<String, Any?>?): String {
    if (payload.isNullOrEmpty()) return "{}"
    return payloadJsonAdapter.toJson(payload)
}

internal fun parseNotificationPayload(type: String, payloadJson: String?): NotificationPayload {
    val raw = payloadJson?.trim().orEmpty()
    if (raw.isBlank()) return NotificationPayload.None
    return runCatching {
        val json = JSONObject(raw)
        if (json.length() == 0) return NotificationPayload.None
        when (type.normalizedNotificationType()) {
            "red_flag" -> parseRedFlagPayload(json, raw)
            "overdue" -> NotificationPayload.Overdue(
                dueDate = json.optCleanString("due_date"),
                daysOverdue = json.optNullableInt("days_overdue"),
            )
            "assignment" -> NotificationPayload.Assignment(
                dueDate = json.optCleanString("due_date"),
            )
            "vitals", "vital_alert", "threshold_breach" -> parseVitalsPayload(json, raw)
            else -> NotificationPayload.Unknown(raw)
        }
    }.getOrElse {
        NotificationPayload.Unknown(raw)
    }
}

private fun parseRedFlagPayload(json: JSONObject, raw: String): NotificationPayload {
    if (!json.has("reasons") || json.isNull("reasons")) {
        return NotificationPayload.RedFlag(emptyList())
    }
    val reasonsArray = json.opt("reasons") as? JSONArray
        ?: return NotificationPayload.Unknown(raw)
    val reasons = buildList {
        for (index in 0 until reasonsArray.length()) {
            reasonsArray.optString(index).trim().takeIf { it.isNotBlank() }?.let(::add)
        }
    }
    return NotificationPayload.RedFlag(reasons)
}

private fun parseVitalsPayload(json: JSONObject, raw: String): NotificationPayload {
    if (!json.has("metrics") || json.isNull("metrics")) {
        return NotificationPayload.VitalsAlert(emptyList())
    }
    val metricsArray = json.opt("metrics") as? JSONArray
        ?: return NotificationPayload.Unknown(raw)
    val metrics = buildList {
        for (index in 0 until metricsArray.length()) {
            val metric = metricsArray.optJSONObject(index) ?: continue
            val label = metric.optCleanString("label") ?: continue
            val value = metric.optCleanString("value") ?: continue
            add(
                VitalsTriggerMetric(
                    label = label,
                    value = value,
                    threshold = metric.optCleanString("threshold"),
                    alerting = metric.optBoolean("alerting", false),
                ),
            )
        }
    }
    return NotificationPayload.VitalsAlert(metrics)
}

private fun String.normalizedNotificationType(): String =
    trim().lowercase()

private fun JSONObject.optCleanString(key: String): String? {
    if (!has(key) || isNull(key)) return null
    return optString(key).trim().takeIf { it.isNotBlank() }
}

private fun JSONObject.optNullableInt(key: String): Int? {
    if (!has(key) || isNull(key)) return null
    return when (val value = opt(key)) {
        is Number -> value.toInt()
        is String -> value.trim().toIntOrNull()
        else -> null
    }
}
