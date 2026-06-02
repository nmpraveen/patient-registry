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
    val payload: Map<String, Any?>? = null,
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

data class ChoiceDto(
    val value: String,
    val label: String,
)

data class CaseFormMetadataDto(
    @Json(name = "can_create") val canCreate: Boolean = false,
    val categories: List<CaseCategoryDto> = emptyList(),
    val prefixes: List<ChoiceDto> = emptyList(),
    @Json(name = "blood_groups") val bloodGroups: List<ChoiceDto> = emptyList(),
    val genders: List<ChoiceDto> = emptyList(),
    @Json(name = "ncd_flags") val ncdFlags: List<ChoiceDto> = emptyList(),
    @Json(name = "anc_high_risk_reasons") val ancHighRiskReasons: List<ChoiceDto> = emptyList(),
    @Json(name = "surgical_pathways") val surgicalPathways: List<ChoiceDto> = emptyList(),
    @Json(name = "review_frequencies") val reviewFrequencies: List<ChoiceDto> = emptyList(),
)

data class PatientSearchResponseDto(
    val count: Int = 0,
    val next: String? = null,
    val previous: String? = null,
    val results: List<PatientLookupDto> = emptyList(),
)

data class PatientLookupDto(
    val id: Long,
    val uhid: String,
    val name: String?,
    val prefix: String?,
    @Json(name = "first_name") val firstName: String?,
    @Json(name = "last_name") val lastName: String?,
    val gender: String?,
    @Json(name = "gender_label") val genderLabel: String?,
    @Json(name = "blood_group") val bloodGroup: String?,
    @Json(name = "date_of_birth") val dateOfBirth: String?,
    val age: Int?,
    val place: String?,
    @Json(name = "phone_number") val phoneNumber: String?,
    @Json(name = "alternate_phone_number") val alternatePhoneNumber: String?,
    @Json(name = "is_temporary_id") val isTemporaryId: Boolean = false,
    @Json(name = "active_case_count") val activeCaseCount: Int? = null,
    @Json(name = "total_case_count") val totalCaseCount: Int? = null,
)

data class CreateCaseRequestDto(
    @Json(name = "patient_mode") val patientMode: String,
    @Json(name = "selected_patient") val selectedPatient: Long? = null,
    @Json(name = "use_temporary_uhid") val useTemporaryUhid: Boolean = false,
    val uhid: String? = null,
    val prefix: String? = null,
    @Json(name = "first_name") val firstName: String? = null,
    @Json(name = "last_name") val lastName: String? = null,
    val gender: String? = null,
    @Json(name = "blood_group") val bloodGroup: String? = null,
    @Json(name = "date_of_birth") val dateOfBirth: String? = null,
    val place: String? = null,
    val age: Int? = null,
    @Json(name = "phone_number") val phoneNumber: String? = null,
    @Json(name = "alternate_phone_number") val alternatePhoneNumber: String? = null,
    val category: Long,
    val subcategory: String? = null,
    val diagnosis: String? = null,
    @Json(name = "referred_by") val referredBy: String? = null,
    val notes: String? = null,
    @Json(name = "high_risk") val highRisk: Boolean = false,
    @Json(name = "ncd_flags") val ncdFlags: List<String> = emptyList(),
    @Json(name = "anc_high_risk_reasons") val ancHighRiskReasons: List<String> = emptyList(),
    @Json(name = "rch_number") val rchNumber: String? = null,
    @Json(name = "rch_bypass") val rchBypass: Boolean = false,
    val lmp: String? = null,
    val edd: String? = null,
    @Json(name = "usg_edd") val usgEdd: String? = null,
    @Json(name = "surgical_pathway") val surgicalPathway: String? = null,
    @Json(name = "surgery_done") val surgeryDone: Boolean = false,
    @Json(name = "surgery_date") val surgeryDate: String? = null,
    @Json(name = "review_frequency") val reviewFrequency: String? = null,
    @Json(name = "review_date") val reviewDate: String? = null,
    val gravida: Int? = null,
    val para: Int? = null,
    val abortions: Int? = null,
    val living: Int? = null,
    val ftnd: Int? = null,
    val lscs: Int? = null,
    @Json(name = "client_write_id") val clientWriteId: String,
)

data class CaseCreateResponseDto(
    val message: String,
    @Json(name = "case_id") val caseId: Long,
    val case: CaseSummaryDto,
)

data class CaseCreateErrorDto(
    val message: String? = null,
    val errors: Map<String, List<String>> = emptyMap(),
)
