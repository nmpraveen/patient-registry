package com.naveenhospital.medtrack.core.data.local

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "cases")
data class CaseEntity(
    @PrimaryKey val id: String,
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

@Entity(tableName = "case_stats")
data class CaseStatsEntity(
    @PrimaryKey val cacheKey: String,
    val today: Int,
    val upcoming: Int,
    val overdue: Int,
    val awaiting: Int,
    val red: Int,
    val updatedAtMillis: Long,
)

@Entity(tableName = "tasks")
data class TaskEntity(
    @PrimaryKey val id: String,
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

@Entity(tableName = "vitals")
data class VitalEntity(
    @PrimaryKey val id: String,
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

@Entity(tableName = "vitals_thresholds")
data class VitalsThresholdEntity(
    @PrimaryKey val id: String,
    val payloadJson: String,
    val updatedAtMillis: Long,
)

@Entity(tableName = "category_options")
data class CategoryOptionsEntity(
    @PrimaryKey val id: String,
    val payloadJson: String,
    val updatedAtMillis: Long,
)

@Entity(tableName = "notifications")
data class NotificationEntity(
    @PrimaryKey val id: String,
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

@Entity(tableName = "push_tokens")
data class PushTokenEntity(
    @PrimaryKey val token: String,
    val deviceLabel: String,
    val syncedAtMillis: Long,
)

@Entity(tableName = "pending_writes")
data class PendingWriteEntity(
    @PrimaryKey val clientWriteId: String,
    val writeType: String,
    val caseId: String?,
    val taskId: String?,
    val payloadJson: String,
    val retryCount: Int,
    val lastError: String?,
    val createdAtMillis: Long,
    val updatedAtMillis: Long,
)

@Entity(tableName = "sync_conflicts")
data class SyncConflictEntity(
    @PrimaryKey val clientWriteId: String,
    val writeType: String,
    val caseId: String?,
    val taskId: String?,
    val message: String,
    val serverPayloadJson: String?,
    val createdAtMillis: Long,
)

@Entity(tableName = "cache_metadata")
data class CacheMetadataEntity(
    @PrimaryKey val cacheKey: String,
    val updatedAtMillis: Long,
)
