package com.naveenhospital.medtrack.core.data.sync

import com.naveenhospital.medtrack.core.data.local.PendingWriteEntity
import com.naveenhospital.medtrack.core.network.model.ClientWriteRequestDto
import com.naveenhospital.medtrack.core.network.model.LogCallRequestDto
import com.naveenhospital.medtrack.core.network.model.VitalsRequestDto
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory

class MalformedPendingWriteException(message: String, cause: Throwable? = null) : Exception(message, cause)

object PendingWriteTypes {
    const val TASK_COMPLETE = "task_complete"
    const val CALL_OUTCOME = "call_outcome"
    const val VITALS_CREATE = "vitals_create"
    const val NOTIFICATION_READ = "notification_read"
}

data class NotificationReadPayload(
    val notificationId: String,
    val clientWriteId: String,
)

sealed class DecodedPendingWrite {
    data class TaskComplete(
        val caseId: String,
        val taskId: String,
        val payload: ClientWriteRequestDto,
    ) : DecodedPendingWrite()

    data class CallOutcome(
        val caseId: String,
        val payload: LogCallRequestDto,
    ) : DecodedPendingWrite()

    data class VitalsCreate(
        val caseId: String,
        val payload: VitalsRequestDto,
    ) : DecodedPendingWrite()

    data class NotificationRead(
        val notificationId: String,
        val payload: NotificationReadPayload,
    ) : DecodedPendingWrite()
}

object PendingWriteJson {
    private val moshi = Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()

    private val taskCompleteAdapter = moshi.adapter(ClientWriteRequestDto::class.java)
    private val callOutcomeAdapter = moshi.adapter(LogCallRequestDto::class.java)
    private val vitalsAdapter = moshi.adapter(VitalsRequestDto::class.java)
    private val notificationReadAdapter = moshi.adapter(NotificationReadPayload::class.java)

    fun encodeTaskComplete(payload: ClientWriteRequestDto): String =
        taskCompleteAdapter.toJson(payload)

    fun decodeTaskComplete(json: String): ClientWriteRequestDto =
        requireNotNull(taskCompleteAdapter.fromJson(json))

    fun encodeCallOutcome(payload: LogCallRequestDto): String =
        callOutcomeAdapter.toJson(payload)

    fun decodeCallOutcome(json: String): LogCallRequestDto =
        requireNotNull(callOutcomeAdapter.fromJson(json))

    fun encodeVitals(payload: VitalsRequestDto): String =
        vitalsAdapter.toJson(payload)

    fun decodeVitals(json: String): VitalsRequestDto =
        requireNotNull(vitalsAdapter.fromJson(json))

    fun encodeNotificationRead(payload: NotificationReadPayload): String =
        notificationReadAdapter.toJson(payload)

    fun decodeNotificationRead(json: String): NotificationReadPayload =
        requireNotNull(notificationReadAdapter.fromJson(json))

    fun decodeForSync(write: PendingWriteEntity): DecodedPendingWrite =
        when (write.writeType) {
            PendingWriteTypes.TASK_COMPLETE -> DecodedPendingWrite.TaskComplete(
                caseId = write.caseId.requiredId("case id"),
                taskId = write.taskId.requiredId("task id"),
                payload = decodePayload(write) { decodeTaskComplete(write.payloadJson) },
            )
            PendingWriteTypes.CALL_OUTCOME -> DecodedPendingWrite.CallOutcome(
                caseId = write.caseId.requiredId("case id"),
                payload = decodePayload(write) { decodeCallOutcome(write.payloadJson) },
            )
            PendingWriteTypes.VITALS_CREATE -> DecodedPendingWrite.VitalsCreate(
                caseId = write.caseId.requiredId("case id"),
                payload = decodePayload(write) { decodeVitals(write.payloadJson) },
            )
            PendingWriteTypes.NOTIFICATION_READ -> {
                val payload = decodePayload(write) { decodeNotificationRead(write.payloadJson) }
                DecodedPendingWrite.NotificationRead(
                    notificationId = payload.notificationId.requiredId("notification id"),
                    payload = payload,
                )
            }
            else -> throw MalformedPendingWriteException("Unsupported pending write type: ${write.writeType}")
        }

    private fun <T> decodePayload(write: PendingWriteEntity, decode: () -> T): T =
        try {
            decode()
        } catch (error: Exception) {
            throw MalformedPendingWriteException(
                message = "Malformed pending write payload for ${write.writeType}.",
                cause = error,
            )
        }

    private fun String?.requiredId(label: String): String =
        takeIf { !it.isNullOrBlank() }
            ?: throw MalformedPendingWriteException("Missing $label for pending write.")
}
