package com.naveenhospital.medtrack.core.data.sync

import com.naveenhospital.medtrack.core.data.local.PendingWriteEntity
import com.naveenhospital.medtrack.core.network.model.ClientWriteRequestDto
import com.naveenhospital.medtrack.core.network.model.LogCallRequestDto
import com.naveenhospital.medtrack.core.network.model.VitalsRequestDto
import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test

class PendingWritePayloadsTest {
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
