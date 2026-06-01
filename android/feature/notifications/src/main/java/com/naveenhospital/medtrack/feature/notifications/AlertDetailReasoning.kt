package com.naveenhospital.medtrack.feature.notifications

import com.naveenhospital.medtrack.core.designsystem.medtrackShortDateLabel
import com.naveenhospital.medtrack.core.domain.model.NotificationItem
import com.naveenhospital.medtrack.core.domain.model.NotificationPayload

internal data class WhyThisFiredRow(
    val label: String,
    val value: String,
    val tone: AlertReasonTone = AlertReasonTone.Muted,
)

internal enum class AlertReasonTone {
    Danger,
    Warning,
    Primary,
    Success,
    Muted,
}

internal fun NotificationItem.normalizedType(): String =
    type.trim().lowercase()

internal fun NotificationItem.alertHeadline(): String =
    when (normalizedType()) {
        "red_flag" -> {
            val reasons = (payload as? NotificationPayload.RedFlag)?.reasons.orEmpty()
            reasons.takeIf { it.isNotEmpty() }?.joinToString(", ", prefix = "Red flag: ")
                ?: title.takeUnless { it.isGenericNotificationTitle() }?.takeIf { it.isNotBlank() }
                ?: "Red flag"
        }
        "overdue" -> "Overdue task"
        "assignment" -> "New assignment"
        "vitals", "vital_alert", "threshold_breach" -> {
            val metric = (payload as? NotificationPayload.VitalsAlert)?.metrics?.firstOrNull { it.alerting }
            metric?.let { "${it.label} threshold breached" }
                ?: title.takeIf { it.isNotBlank() }
                ?: "Vitals alert"
        }
        else -> title.takeIf { it.isNotBlank() } ?: "Notification"
    }

internal fun NotificationItem.alertSummary(): String =
    when (normalizedType()) {
        "red_flag" -> {
            val reasons = (payload as? NotificationPayload.RedFlag)?.reasons.orEmpty()
            reasons.takeIf { it.isNotEmpty() }?.joinToString(", ")
                ?: originalMessage()
                ?: "Red flag details unavailable."
        }
        "overdue" -> {
            val overdue = payload as? NotificationPayload.Overdue
            val dueDate = overdue?.dueDate
            val daysOverdue = overdue?.daysOverdue
            when {
                dueDate != null && daysOverdue != null ->
                    "Due ${formatPayloadDate(dueDate)}, $daysOverdue ${dayUnit(daysOverdue)} overdue"
                daysOverdue != null -> "$daysOverdue ${dayUnit(daysOverdue)} overdue"
                dueDate != null -> "Due ${formatPayloadDate(dueDate)}"
                else -> originalMessage() ?: "Overdue task details unavailable."
            }
        }
        "assignment" -> {
            val assignment = payload as? NotificationPayload.Assignment
            assignment?.dueDate?.let { "Due ${formatPayloadDate(it)}" }
                ?: originalMessage()
                ?: "Assignment details unavailable."
        }
        "vitals", "vital_alert", "threshold_breach" -> {
            val metric = (payload as? NotificationPayload.VitalsAlert)?.metrics?.firstOrNull { it.alerting }
            metric?.let { "${it.label}: ${it.value}" }
                ?: originalMessage()
                ?: "Vitals alert details unavailable."
        }
        else -> body.takeIf { it.isNotBlank() } ?: title
    }

internal fun NotificationItem.whyThisFiredRows(): List<WhyThisFiredRow> =
    when (normalizedType()) {
        "red_flag" -> {
            val payload = payload as? NotificationPayload.RedFlag
            payload?.reasons.orEmpty()
                .filter { it.isNotBlank() }
                .map { WhyThisFiredRow(label = "Reason", value = it, tone = AlertReasonTone.Danger) }
                .ifEmpty { uncachedReasonRows("Trigger details were not cached for this notification.") }
        }
        "overdue" -> {
            val overdue = payload as? NotificationPayload.Overdue
            buildList {
                overdue?.dueDate?.let {
                    add(WhyThisFiredRow(label = "Due date", value = formatPayloadDate(it), tone = AlertReasonTone.Warning))
                }
                overdue?.daysOverdue?.let {
                    add(WhyThisFiredRow(label = "Days overdue", value = it.toString(), tone = AlertReasonTone.Warning))
                }
            }.ifEmpty { uncachedReasonRows("Overdue details were not cached for this notification.") }
        }
        "assignment" -> {
            val assignment = payload as? NotificationPayload.Assignment
            assignment?.dueDate?.let {
                listOf(WhyThisFiredRow(label = "Due date", value = formatPayloadDate(it), tone = AlertReasonTone.Primary))
            } ?: uncachedReasonRows("Assignment details were not cached for this notification.")
        }
        "vitals", "vital_alert", "threshold_breach" -> {
            val vitals = payload as? NotificationPayload.VitalsAlert
            vitals?.metrics.orEmpty().map {
                WhyThisFiredRow(
                    label = it.label,
                    value = listOfNotNull(it.value, it.threshold).joinToString(" "),
                    tone = if (it.alerting) AlertReasonTone.Danger else AlertReasonTone.Success,
                )
            }.ifEmpty { uncachedReasonRows("Vitals trigger details were not cached for this notification.") }
        }
        else -> uncachedReasonRows("Structured trigger details are not available for this notification.")
    }

private fun NotificationItem.uncachedReasonRows(message: String): List<WhyThisFiredRow> =
    buildList {
        add(WhyThisFiredRow(label = "Status", value = message, tone = AlertReasonTone.Muted))
        originalMessage()?.let {
            add(WhyThisFiredRow(label = "Original message", value = it, tone = AlertReasonTone.Muted))
        }
    }

private fun NotificationItem.originalMessage(): String? {
    val bodyText = body.trim()
    if (bodyText.isBlank()) return title.trim().takeIf { it.isNotBlank() }
    val lead = bodyText.substringBefore(":").trim()
    return if (bodyText.contains(":") && lead.isLikelyPatientLead()) {
        bodyText.substringAfter(":").trim().takeIf { it.isNotBlank() } ?: bodyText
    } else {
        bodyText
    }
}

private fun formatPayloadDate(raw: String): String =
    medtrackShortDateLabel(raw) ?: raw

private fun dayUnit(days: Int): String =
    if (days == 1) "day" else "days"

private fun String.isGenericNotificationTitle(): Boolean =
    equals("Red flag patient", ignoreCase = true) ||
        equals("Task overdue", ignoreCase = true) ||
        equals("Overdue MEDTRACK task", ignoreCase = true) ||
        equals("New assignment", ignoreCase = true) ||
        equals("New MEDTRACK assignment", ignoreCase = true)

private fun String.isLikelyPatientLead(): Boolean =
    length in 3..64 &&
        contains(Regex("[A-Za-z]")) &&
        split(Regex("\\s+")).size <= 5
