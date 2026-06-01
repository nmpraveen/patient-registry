package com.naveenhospital.medtrack.core.domain.model

sealed interface NotificationPayload {
    object None : NotificationPayload

    data class RedFlag(
        val reasons: List<String>,
    ) : NotificationPayload

    data class Overdue(
        val dueDate: String?,
        val daysOverdue: Int?,
    ) : NotificationPayload

    data class Assignment(
        val dueDate: String?,
    ) : NotificationPayload

    data class VitalsAlert(
        val metrics: List<VitalsTriggerMetric>,
    ) : NotificationPayload

    data class Unknown(
        val rawJson: String,
    ) : NotificationPayload
}

data class VitalsTriggerMetric(
    val label: String,
    val value: String,
    val threshold: String?,
    val alerting: Boolean,
)
