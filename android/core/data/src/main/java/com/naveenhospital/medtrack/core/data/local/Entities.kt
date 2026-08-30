package com.naveenhospital.medtrack.core.data.local

import androidx.room.ColumnInfo
import androidx.room.Entity

@Entity(tableName = "cases", primaryKeys = ["ownerAccountId", "id"])
data class CaseEntity(
    val ownerAccountId: String,
    val id: String,
    val uhid: String,
    val patientName: String,
    val age: Int?,
    val sexLabel: String?,
    val place: String?,
    val phoneNumber: String?,
    val category: String,
    val subcategoryValue: String?,
    val subcategoryLabel: String?,
    val status: String,
    val diagnosis: String,
    val nextTaskId: String?,
    val nextTaskTitle: String?,
    val nextTaskDueDate: String?,
    val latestVitalSummary: String?,
    val isHighRisk: Boolean,
    val highRiskReasons: String,
    val updatedAtMillis: Long,
)

@Entity(tableName = "case_stats", primaryKeys = ["ownerAccountId", "cacheKey"])
data class CaseStatsEntity(
    val ownerAccountId: String,
    val cacheKey: String,
    val today: Int,
    val upcoming: Int,
    val overdue: Int,
    val awaiting: Int,
    val red: Int,
    val updatedAtMillis: Long,
)

@Entity(tableName = "tasks", primaryKeys = ["ownerAccountId", "id"])
data class TaskEntity(
    val ownerAccountId: String,
    val id: String,
    val caseId: String,
    val title: String,
    val dueDate: String?,
    val status: String,
    val statusLabel: String,
    val canComplete: Boolean,
    val taskType: String? = null,
    val taskTypeLabel: String? = null,
    val assignedUserId: Long? = null,
    val assignedUser: String? = null,
    val notes: String? = null,
    val updatedAtMillis: Long,
)

@Entity(tableName = "vitals", primaryKeys = ["ownerAccountId", "id"])
data class VitalEntity(
    val ownerAccountId: String,
    val id: String,
    val caseId: String,
    val recordedAt: String,
    val bpSystolic: Int?,
    val bpDiastolic: Int?,
    val pulse: Int?,
    val spo2: Int?,
    val weightKg: String?,
    val hemoglobin: String?,
    val summary: String,
    val updatedAtMillis: Long,
)

@Entity(tableName = "vitals_thresholds", primaryKeys = ["ownerAccountId", "id"])
data class VitalsThresholdEntity(
    val ownerAccountId: String,
    val id: String,
    val payloadJson: String,
    val updatedAtMillis: Long,
)

@Entity(tableName = "category_options", primaryKeys = ["ownerAccountId", "id"])
data class CategoryOptionsEntity(
    val ownerAccountId: String,
    val id: String,
    val payloadJson: String,
    val updatedAtMillis: Long,
)

@Entity(tableName = "notifications", primaryKeys = ["ownerAccountId", "id"])
data class NotificationEntity(
    val ownerAccountId: String,
    val id: String,
    val type: String,
    val title: String,
    val body: String,
    val caseId: String?,
    val taskId: String?,
    val createdAt: String,
    val isRead: Boolean,
    @ColumnInfo(name = "payloadJson", defaultValue = "'{}'")
    val payloadJson: String = "{}",
)

@Entity(tableName = "push_tokens", primaryKeys = ["ownerAccountId", "token"])
data class PushTokenEntity(
    val ownerAccountId: String,
    val token: String,
    val deviceLabel: String,
    val syncedAtMillis: Long,
)

@Entity(tableName = "pending_writes", primaryKeys = ["ownerAccountId", "clientWriteId"])
data class PendingWriteEntity(
    val ownerAccountId: String,
    val clientWriteId: String,
    val writeType: String,
    val caseId: String?,
    val taskId: String?,
    val payloadJson: String,
    val retryCount: Int,
    val lastError: String?,
    val createdAtMillis: Long,
    val updatedAtMillis: Long,
)

@Entity(tableName = "sync_conflicts", primaryKeys = ["ownerAccountId", "clientWriteId"])
data class SyncConflictEntity(
    val ownerAccountId: String,
    val clientWriteId: String,
    val writeType: String,
    val caseId: String?,
    val taskId: String?,
    val message: String,
    val serverPayloadJson: String?,
    val createdAtMillis: Long,
)

@Entity(tableName = "cache_metadata", primaryKeys = ["ownerAccountId", "cacheKey"])
data class CacheMetadataEntity(
    val ownerAccountId: String,
    val cacheKey: String,
    val updatedAtMillis: Long,
)
