package com.naveenhospital.medtrack.core.data.sync

import com.naveenhospital.medtrack.core.data.local.PendingWriteEntity
import com.naveenhospital.medtrack.core.data.local.TaskEntity
import com.naveenhospital.medtrack.core.network.model.ClientWriteRequestDto
import com.naveenhospital.medtrack.core.network.model.LogCallRequestDto
import com.naveenhospital.medtrack.core.network.model.VitalsRequestDto
import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test

class PendingWritePayloadsTest {
    @Test
    fun legacyReplayDoesNotAcquireAuthoringFields() {
        val oldCall = """{"outcome":"attempted","client_write_id":"old-call","attempted_at":"2026-01-01T00:00:00Z"}"""
        val decoded = PendingWriteJson.decodeCallOutcome(oldCall)
        val encoded = PendingWriteJson.encodeCallOutcome(decoded)
        org.junit.Assert.assertFalse(encoded.contains("reason"))
        assertEquals("old-call", decoded.clientWriteId)
        assertEquals("2026-01-01T00:00:00Z", decoded.attemptedAt)
        val oldComplete = PendingWriteJson.decodeTaskComplete("""{"client_write_id":"old-complete"}""")
        org.junit.Assert.assertNull(oldComplete.baseValues)
        org.junit.Assert.assertFalse(PendingWriteJson.encodeTaskComplete(oldComplete).contains("base_values"))
    }

    @Test
    fun newPayloadAndRollbackRetainStage2Values() {
        val task = TaskEntity(ownerAccountId = "1", id = "7", caseId = "42", title = "Review",
            dueDate = "2026-09-08", status = "SCHEDULED", statusLabel = "Scheduled", canComplete = true,
            notes = "Keep notes", frequencyLabel = "Monthly", serverUpdatedAt = "2026-09-07T00:00:00Z", updatedAtMillis = 1)
        val request = ClientWriteRequestDto("completion", mapOf("status" to task.status, "due_date" to task.dueDate))
        val decoded = PendingWriteJson.decodeTaskCompletePending(PendingWriteJson.encodeTaskComplete(request, task))
        assertEquals(request, decoded.request)
        assertEquals(task, decoded.rollback!!.toEntity("1", "42", "7"))
        val call = LogCallRequestDto(outcome = "reached", reason = "Appointment", clientWriteId = "call")
        assertEquals(call, PendingWriteJson.decodeCallOutcome(PendingWriteJson.encodeCallOutcome(call)))
    }

    @Test
    fun decodeForSyncReturnsTaskCompleteWithRequiredIds() {
        val payload = ClientWriteRequestDto(clientWriteId = "write-1")
        val write = pendingWrite(
            writeType = PendingWriteTypes.TASK_COMPLETE,
            caseId = "case-1",
            taskId = "task-1",
            payloadJson = PendingWriteJson.encodeTaskComplete(payload),
        )

        val decoded = PendingWriteJson.decodeForSync(write) as DecodedPendingWrite.TaskComplete

        assertEquals("case-1", decoded.caseId)
        assertEquals("task-1", decoded.taskId)
        assertEquals("write-1", decoded.payload.clientWriteId)
    }

    @Test
    fun taskCompletePayloadRetainsRollbackAndReissueRotatesIdempotencyIdentity() {
        val original = TaskEntity(
            ownerAccountId = "1",
            id = "task-1",
            caseId = "case-1",
            title = "Review",
            dueDate = null,
            status = "PENDING",
            statusLabel = "Pending",
            canComplete = true,
            updatedAtMillis = 9L,
        )
        val encoded = PendingWriteJson.encodeTaskComplete(
            ClientWriteRequestDto("write-1"),
            rollback = original,
        )

        val reissued = PendingWriteJson.reissue(PendingWriteTypes.TASK_COMPLETE, encoded, "write-2")
        val decoded = PendingWriteJson.decodeTaskCompletePending(reissued)

        assertEquals("write-2", decoded.request.clientWriteId)
        assertEquals("PENDING", decoded.rollback?.status)
        assertEquals(true, decoded.rollback?.canComplete)
    }

    @Test
    fun decodeForSyncRejectsTaskCompleteWithoutCaseId() {
        val write = pendingWrite(
            writeType = PendingWriteTypes.TASK_COMPLETE,
            caseId = null,
            taskId = "task-1",
            payloadJson = PendingWriteJson.encodeTaskComplete(ClientWriteRequestDto(clientWriteId = "write-1")),
        )

        val error = expectMalformed { PendingWriteJson.decodeForSync(write) }

        assertEquals("Missing case id for pending write.", error.message)
    }

    @Test
    fun decodeForSyncRejectsCallOutcomeWithoutCaseId() {
        val write = pendingWrite(
            writeType = PendingWriteTypes.CALL_OUTCOME,
            caseId = null,
            payloadJson = PendingWriteJson.encodeCallOutcome(
                LogCallRequestDto(
                    outcome = "NO_ANSWER",
                    clientWriteId = "write-1",
                ),
            ),
        )

        val error = expectMalformed { PendingWriteJson.decodeForSync(write) }

        assertEquals("Missing case id for pending write.", error.message)
    }

    @Test
    fun decodeForSyncRejectsMalformedPayload() {
        val write = pendingWrite(
            writeType = PendingWriteTypes.VITALS_CREATE,
            caseId = "case-1",
            payloadJson = "{not-json",
        )

        val error = expectMalformed { PendingWriteJson.decodeForSync(write) }

        assertEquals("Malformed pending write payload for vitals_create.", error.message)
    }

    @Test
    fun decodeForSyncReturnsNotificationReadWithRequiredId() {
        val payload = NotificationReadPayload(
            notificationId = "notification-1",
            clientWriteId = "write-1",
        )
        val write = pendingWrite(
            writeType = PendingWriteTypes.NOTIFICATION_READ,
            payloadJson = PendingWriteJson.encodeNotificationRead(payload),
        )

        val decoded = PendingWriteJson.decodeForSync(write) as DecodedPendingWrite.NotificationRead

        assertEquals("notification-1", decoded.notificationId)
        assertEquals("write-1", decoded.payload.clientWriteId)
    }

    @Test
    fun decodeForSyncRejectsNotificationReadWithoutNotificationId() {
        val write = pendingWrite(
            writeType = PendingWriteTypes.NOTIFICATION_READ,
            payloadJson = PendingWriteJson.encodeNotificationRead(
                NotificationReadPayload(
                    notificationId = "",
                    clientWriteId = "write-1",
                ),
            ),
        )

        val error = expectMalformed { PendingWriteJson.decodeForSync(write) }

        assertEquals("Missing notification id for pending write.", error.message)
    }

    @Test
    fun decodeForSyncRejectsUnsupportedWriteType() {
        val write = pendingWrite(
            writeType = "unknown",
            payloadJson = PendingWriteJson.encodeVitals(VitalsRequestDto(clientWriteId = "write-1")),
        )

        val error = expectMalformed { PendingWriteJson.decodeForSync(write) }

        assertEquals("Unsupported pending write type: unknown", error.message)
    }

    private fun pendingWrite(
        writeType: String,
        caseId: String? = "case-1",
        taskId: String? = null,
        payloadJson: String,
    ): PendingWriteEntity =
        PendingWriteEntity(
            ownerAccountId = "1",
            clientWriteId = "write-1",
            writeType = writeType,
            caseId = caseId,
            taskId = taskId,
            payloadJson = payloadJson,
            retryCount = 0,
            lastError = null,
            createdAtMillis = 1L,
            updatedAtMillis = 1L,
        )

    private fun expectMalformed(block: () -> Unit): MalformedPendingWriteException =
        try {
            block()
            fail("Expected MalformedPendingWriteException")
            throw AssertionError("unreachable")
        } catch (error: MalformedPendingWriteException) {
            error
        }
}
