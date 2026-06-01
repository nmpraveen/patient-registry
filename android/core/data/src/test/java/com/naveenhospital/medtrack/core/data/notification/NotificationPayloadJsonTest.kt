package com.naveenhospital.medtrack.core.data.notification

import com.naveenhospital.medtrack.core.domain.model.NotificationPayload
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class NotificationPayloadJsonTest {
    @Test
    fun dtoPayloadSerializesToValidJson() {
        val payloadJson = notificationPayloadToJson(
            mapOf(
                "channel" to "red_flags",
                "reasons" to listOf("High risk"),
            ),
        )

        val json = JSONObject(payloadJson)

        assertEquals("red_flags", json.getString("channel"))
        assertEquals("High risk", json.getJSONArray("reasons").getString(0))
    }

    @Test
    fun emptyPayloadJsonParsesAsNone() {
        assertEquals(
            NotificationPayload.None,
            parseNotificationPayload(type = "red_flag", payloadJson = "{}"),
        )
    }

    @Test
    fun redFlagPayloadParsesReasons() {
        assertEquals(
            NotificationPayload.RedFlag(listOf("High risk")),
            parseNotificationPayload(
                type = "red_flag",
                payloadJson = """{"channel":"red_flags","reasons":["High risk"]}""",
            ),
        )
    }

    @Test
    fun redFlagPayloadWithMissingReasonsParsesEmptyReasons() {
        assertEquals(
            NotificationPayload.RedFlag(emptyList()),
            parseNotificationPayload(type = "red_flag", payloadJson = """{"channel":"red_flags"}"""),
        )
    }

    @Test
    fun redFlagPayloadWithWrongReasonsShapeIsUnknown() {
        assertTrue(
            parseNotificationPayload(
                type = "red_flag",
                payloadJson = """{"channel":"red_flags","reasons":"High risk"}""",
            ) is NotificationPayload.Unknown,
        )
    }

    @Test
    fun overduePayloadParsesDueDateAndDaysOverdue() {
        assertEquals(
            NotificationPayload.Overdue(dueDate = "2026-05-28", daysOverdue = 3),
            parseNotificationPayload(
                type = "overdue",
                payloadJson = """{"channel":"overdue","due_date":"2026-05-28","days_overdue":3}""",
            ),
        )
    }

    @Test
    fun assignmentPayloadParsesDueDate() {
        assertEquals(
            NotificationPayload.Assignment(dueDate = "2026-06-02"),
            parseNotificationPayload(
                type = "assignment",
                payloadJson = """{"channel":"assignments","due_date":"2026-06-02"}""",
            ),
        )
    }

    @Test
    fun malformedPayloadIsUnknown() {
        assertTrue(
            parseNotificationPayload(type = "red_flag", payloadJson = "{not-json") is NotificationPayload.Unknown,
        )
    }
}
