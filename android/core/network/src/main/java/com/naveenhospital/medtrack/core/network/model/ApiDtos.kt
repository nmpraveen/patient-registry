package com.naveenhospital.medtrack.core.network.model

import com.squareup.moshi.Json

data class LoginRequestDto(
    val username: String,
    val password: String,
)

data class AuthSessionDto(
    val access: String,
    val refresh: String? = null,
)

data class RefreshTokenRequestDto(
    val refresh: String,
    @Json(name = "device_token") val deviceToken: String? = null,
)

data class UserProfileDto(
    val id: Long,
    val username: String,
    @Json(name = "display_name") val displayName: String,
    val roles: List<String>,
    val capabilities: Map<String, Boolean>,
)

data class CaseListResponseDto(
    val count: Int,
    val next: String?,
    val previous: String?,
    val stats: CaseStatsDto,
    val results: List<CaseSummaryDto>,
)

data class CaseStatsDto(
    val today: Int,
    val upcoming: Int,
    val overdue: Int,
    val awaiting: Int,
    val red: Int,
)

data class CaseSummaryDto(
    val id: Long,
    val uhid: String,
    val name: String,
    val age: Int?,
    val sex: String?,
    @Json(name = "sex_label") val sexLabel: String?,
    val place: String?,
    @Json(name = "phone_number") val phoneNumber: String?,
    val category: CaseCategoryDto,
    val subcategory: CaseSubcategoryDto?,
    val status: String,
    val diagnosis: String,
    @Json(name = "red_flag") val redFlag: Boolean,
    @Json(name = "red_flag_reasons") val redFlagReasons: List<String>,
    @Json(name = "next_task") val nextTask: TaskDto?,
    @Json(name = "latest_vital") val latestVital: VitalDto?,
)

data class CaseDetailDto(
    val case: CaseSummaryDto,
    val tasks: List<TaskDto>,
    val vitals: List<VitalDto> = emptyList(),
    @Json(name = "call_logs") val callLogs: List<CallLogDto> = emptyList(),
)

data class TaskDto(
    val id: Long,
    val title: String,
    @Json(name = "due_date") val dueDate: String?,
    val status: String,
    @Json(name = "status_label") val statusLabel: String? = null,
    @Json(name = "can_complete") val canComplete: Boolean? = null,
)

data class CaseCategoryDto(
    val id: Long?,
    val name: String,
    @Json(name = "icon_path") val iconPath: String? = null,
    val theme: Map<String, String>? = null,
    val subcategories: List<CaseSubcategoryDto> = emptyList(),
)

data class CaseSubcategoryDto(
    val value: String?,
    val label: String?,
    @Json(name = "icon_path") val iconPath: String? = null,
)

data class VitalDto(
    val id: Long,
    @Json(name = "recorded_at") val recordedAt: String,
    @Json(name = "bp_systolic") val bpSystolic: Int?,
    @Json(name = "bp_diastolic") val bpDiastolic: Int?,
    val pr: Int?,
    val spo2: Int?,
    @Json(name = "weight_kg") val weightKg: String?,
    val hemoglobin: String?,
)

data class CallLogDto(
    val id: Long,
    @Json(name = "task_id") val taskId: Long?,
    val outcome: String,
    @Json(name = "outcome_label") val outcomeLabel: String?,
    val notes: String?,
    @Json(name = "created_at") val createdAt: String,
)

data class TaskWriteResponseDto(
    val message: String,
    val task: TaskDto,
    val case: CaseSummaryDto,
)

data class ClientWriteRequestDto(
    @Json(name = "client_write_id") val clientWriteId: String,
)

data class LogCallRequestDto(
    val outcome: String,
    val note: String? = null,
    @Json(name = "task_id") val taskId: Long? = null,
    @Json(name = "attempted_at") val attemptedAt: String? = null,
    @Json(name = "client_write_id") val clientWriteId: String,
)

data class VitalsRequestDto(
    @Json(name = "client_write_id") val clientWriteId: String,
    @Json(name = "recorded_at") val recordedAt: String? = null,
    @Json(name = "bp_systolic") val bpSystolic: Int? = null,
    @Json(name = "bp_diastolic") val bpDiastolic: Int? = null,
    val pr: Int? = null,
    val spo2: Int? = null,
    @Json(name = "weight_kg") val weightKg: String? = null,
    val hemoglobin: String? = null,
)

data class CallWriteResponseDto(
    val message: String,
    @Json(name = "call_log") val callLog: CallLogDto,
    val case: CaseSummaryDto,
)

data class VitalsWriteResponseDto(
    val message: String,
    @Json(name = "latest_vital_id") val latestVitalId: Long,
    val vital: VitalDto,
    val case: CaseSummaryDto,
)

data class VitalsThresholdsDto(
    val version: Int,
    val metrics: Map<String, Any?>,
    @Json(name = "status_labels") val statusLabels: Map<String, Map<String, String>>,
)

data class NotificationsResponseDto(
    val count: Int,
    val next: String?,
    val previous: String?,
    val results: List<NotificationDto>,
)

data class NotificationDto(
    val id: Long,
    val type: String,
    val title: String,
    val body: String,
    @Json(name = "case_id") val caseId: Long?,
    @Json(name = "task_id") val taskId: Long?,
    @Json(name = "read_at") val readAt: String?,
    @Json(name = "created_at") val createdAt: String,
)

data class RegisterPushTokenRequestDto(
    val token: String,
    val platform: String = "android",
    @Json(name = "app_version") val appVersion: String = "",
    @Json(name = "device_label") val deviceLabel: String = "",
)

data class CategoriesResponseDto(
    val categories: List<CaseCategoryDto>,
)

data class ApiMessageDto(
    val message: String? = null,
)
