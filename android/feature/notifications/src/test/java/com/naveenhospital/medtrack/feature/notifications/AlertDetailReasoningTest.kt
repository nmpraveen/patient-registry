package com.naveenhospital.medtrack.feature.notifications

import com.naveenhospital.medtrack.core.domain.model.NotificationItem
import com.naveenhospital.medtrack.core.domain.model.NotificationPayload
import com.naveenhospital.medtrack.core.domain.model.VitalsTriggerMetric
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AlertDetailReasoningTest {
    @Test
    fun redFlagUsesPayloadReasonForHeadlineSummaryAndRows() {
        val notification = notification(
            type = "red_flag",
            title = "Red flag patient",
            body = "Ms. Harini Sivakumar: High risk",
            payload = NotificationPayload.RedFlag(listOf("High risk")),
        )

        val rows = notification.whyThisFiredRows()

        assertEquals("Red flag: High risk", notification.alertHeadline())
        assertEquals("High risk", notification.alertSummary())
        assertEquals(listOf(WhyThisFiredRow("Reason", "High risk", AlertReasonTone.Danger)), rows)
        assertNoLatestVitals(rows)
    }

    @Test
    fun overdueUsesPayloadDueFields() {
        val notification = notification(
            type = "overdue",
            body = "Ms. X: Review is 3 days overdue",
            payload = NotificationPayload.Overdue(dueDate = "2026-05-28", daysOverdue = 3),
        )

        val rows = notification.whyThisFiredRows()

        assertEquals("Overdue task", notification.alertHeadline())
        assertTrue(notification.alertSummary().contains("3 days overdue"))
        assertTrue(rows.any { it.label == "Due date" })
        assertTrue(rows.any { it.label == "Days overdue" && it.value == "3" })
        assertNoLatestVitals(rows)
    }

    @Test
    fun assignmentUsesPayloadDueDate() {
        val notification = notification(
            type = "assignment",
            body = "Ms. X: Review due 2 Jun 2026",
            payload = NotificationPayload.Assignment(dueDate = "2026-06-02"),
        )

        val rows = notification.whyThisFiredRows()

        assertEquals("New assignment", notification.alertHeadline())
        assertTrue(notification.alertSummary().startsWith("Due"))
        assertTrue(rows.any { it.label == "Due date" })
        assertNoLatestVitals(rows)
    }

    @Test
    fun missingPayloadFallsBackWithoutInventingVitals() {
        val notification = notification(
            type = "red_flag",
            body = "Ms. Harini Sivakumar: High risk",
            payload = NotificationPayload.None,
        )

        val rows = notification.whyThisFiredRows()

        assertTrue(rows.any { it.value.contains("not cached") })
        assertTrue(rows.any { it.label == "Original message" && it.value == "High risk" })
        assertNoLatestVitals(rows)
    }

    @Test
    fun vitalsRowsRenderOnlyForExplicitVitalsPayload() {
        val notification = notification(
            type = "vital_alert",
            payload = NotificationPayload.VitalsAlert(
                listOf(
                    VitalsTriggerMetric(
                        label = "SpO2",
                        value = "92%",
                        threshold = "< 95",
                        alerting = true,
                    ),
                ),
            ),
        )

        val rows = notification.whyThisFiredRows()

        assertEquals("SpO2 threshold breached", notification.alertHeadline())
        assertEquals(listOf(WhyThisFiredRow("SpO2", "92% < 95", AlertReasonTone.Danger)), rows)
    }

    private fun notification(
        type: String,
        title: String = "",
        body: String = "",
        payload: NotificationPayload,
    ): NotificationItem =
        NotificationItem(
            id = "1",
            type = type,
            title = title,
            body = body,
            caseId = "42",
            taskId = null,
            createdAt = "2026-06-01T10:00:00Z",
            isRead = false,
            payload = payload,
        )

    private fun assertNoLatestVitals(rows: List<WhyThisFiredRow>) {
        val text = rows.joinToString(" ") { "${it.label} ${it.value}" }
        listOf("BP", "PR", "SpO2", "Hb", "129/82", "79", "98", "11.2").forEach {
            assertFalse("Unexpected latest-vitals text: $it", text.contains(it))
        }
    }
}
