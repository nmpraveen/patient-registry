package com.naveenhospital.medtrack.core.data.sync

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory

object SyncFailureKinds {
    const val AUTHENTICATION = "AUTHENTICATION"
    const val AUTHORIZATION = "AUTHORIZATION"
    const val CONFLICT = "CONFLICT"
    const val MALFORMED = "MALFORMED"
    const val PROTOCOL = "PROTOCOL"
    const val TRANSIENT = "TRANSIENT"
    const val VALIDATION = "VALIDATION"
}

object SyncResolutionStates {
    const val DISCARDED = "DISCARDED"
    const val OPEN = "OPEN"
    const val RETRY_QUEUED = "RETRY_QUEUED"
    const val SYNCED_AFTER_RETRY = "SYNCED_AFTER_RETRY"
}

/** Versioned recovery envelope stored in the existing sync-conflict payload column. */
data class SyncRecoveryPayload(
    val version: Int = 1,
    val failureKind: String,
    val localPayloadJson: String? = null,
    val serverPayloadJson: String? = null,
    val httpStatus: Int? = null,
    val attemptCount: Int? = null,
    val replacementClientWriteId: String? = null,
    val resolutionState: String = SyncResolutionStates.OPEN,
    val resolutionAtMillis: Long? = null,
)

object SyncRecoveryJson {
    private val adapter = Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()
        .adapter(SyncRecoveryPayload::class.java)

    fun encode(payload: SyncRecoveryPayload): String = adapter.toJson(payload)

    fun decode(json: String?): SyncRecoveryPayload? =
        json?.takeIf { it.isNotBlank() }?.let { payload ->
            runCatching { adapter.fromJson(payload) }.getOrNull()
        }
}
