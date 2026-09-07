package com.naveenhospital.medtrack.core.network.model

import com.squareup.moshi.Json

data class LoginRequestDto(
    val username: String,
    val password: String,
    @Json(name = "device_id") val deviceId: String? = null,
    @Json(name = "device_secret") val deviceSecret: String? = null,
    @Json(name = "device_label") val deviceLabel: String? = null,
)

data class LoginResponseDto(
    val access: String? = null,
    val refresh: String? = null,
    @Json(name = "device_approval_required") val deviceApprovalRequired: Boolean? = null,
    val status: String? = null,
    @Json(name = "device_id") val deviceId: String? = null,
    @Json(name = "device_secret") val deviceSecret: String? = null,
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
    @Json(name = "data_scope") val dataScope: DataScopeDto,
)

data class DataScopeDto(
    @Json(name = "case_data_scope") val caseDataScope: String,
    @Json(name = "call_queue") val callQueue: Boolean,
    @Json(name = "intake_patient_lookup") val intakePatientLookup: Boolean,
)

data class CaseListResponseDto(
    val count: Int,
    val next: String?,
    val previous: String?,
    val stats: CaseStatsDto,
    val results: List<CaseSummaryDto>,
)

data class CaseSearchRequestDto(
    val query: String,
    @Json(name = "page_size") val pageSize: Int = 20,
    val cursor: String? = null,
    val bucket: String = "today",
    @Json(name = "assigned_to") val assignedTo: String? = null,
    @Json(name = "scope_context") val scopeContext: String = "",
    val category: List<String> = emptyList(),
    val subcategory: List<String> = emptyList(),
)

data class CaseSearchResponseDto(
    @Json(name = "next_cursor") val nextCursor: String? = null,
    val stats: CaseStatsDto,
    val results: List<CaseSummaryDto> = emptyList(),
)

data class CaseStatsDto(
    val dormant: Int = 0,
    val today: Int,
    val upcoming: Int,
    val overdue: Int,
    val awaiting: Int,
    val red: Int,
)

data class FollowUpDto(
    val label: String = "",
    @Json(name = "edd_missing") val eddMissing: Boolean = false,
    @Json(name = "effective_edd") val effectiveEdd: String? = null,
    @Json(name = "outcome_label") val outcomeLabel: String = "",
    @Json(name = "outcome_date") val outcomeDate: String? = null,
    val reason: String = "",
    @Json(name = "referral_destination") val referralDestination: String = "",
)

data class CaseSummaryDto(
    @Json(name = "follow_up") val followUp: FollowUpDto? = null,
    @Json(name = "updated_at") val updatedAt: String = "",
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
    @Json(name = "task_type") val taskType: String? = null,
    @Json(name = "task_type_label") val taskTypeLabel: String? = null,
    @Json(name = "assigned_user") val assignedUser: String? = null,
    @Json(name = "assigned_user_id") val assignedUserId: Long? = null,
    val notes: String? = null,
    @Json(name = "updated_at") val updatedAt: String,
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
    @Json(name = "updated_at") val updatedAt: String,
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
    @Json(name = "dataset_epoch") val datasetEpoch: String,
    @Json(name = "next_cursor") val nextCursor: String?,
    val results: List<NotificationDto>,
)

data class NotificationDto(
    val id: Long,
    @Json(name = "event_id") val eventId: String,
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

data class PatientSearchRequestDto(
    val query: String,
    @Json(name = "page_size") val pageSize: Int = 10,
    val cursor: String? = null,
)

data class PatientSearchResponseDto(
    @Json(name = "next_cursor") val nextCursor: String? = null,
    val results: List<PatientLookupDto> = emptyList(),
)

data class PatientLookupDto(
    val id: Long,
    val uhid: String,
    val name: String,
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
    val status: String? = null,
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

sealed interface PatchField<out T> {
    data object Omitted : PatchField<Nothing>
    data class Value<T>(val value: T?) : PatchField<T>
}

/** PATCH payload with a real three-state field model: omitted, value, or explicit JSON null. */
data class UpdateCaseRequestDto(
    val baseUpdatedAt: String,
    val baseValues: Map<String, Any?>,
    val patientMode: PatchField<String> = PatchField.Omitted,
    val selectedPatient: PatchField<Long> = PatchField.Omitted,
    val useTemporaryUhid: PatchField<Boolean> = PatchField.Omitted,
    val uhid: PatchField<String> = PatchField.Omitted,
    val prefix: PatchField<String> = PatchField.Omitted,
    val firstName: PatchField<String> = PatchField.Omitted,
    val lastName: PatchField<String> = PatchField.Omitted,
    val gender: PatchField<String> = PatchField.Omitted,
    val bloodGroup: PatchField<String> = PatchField.Omitted,
    val dateOfBirth: PatchField<String> = PatchField.Omitted,
    val place: PatchField<String> = PatchField.Omitted,
    val age: PatchField<Int> = PatchField.Omitted,
    val phoneNumber: PatchField<String> = PatchField.Omitted,
    val alternatePhoneNumber: PatchField<String> = PatchField.Omitted,
    val category: PatchField<Long> = PatchField.Omitted,
    val subcategory: PatchField<String> = PatchField.Omitted,
    val status: PatchField<String> = PatchField.Omitted,
    val diagnosis: PatchField<String> = PatchField.Omitted,
    val referredBy: PatchField<String> = PatchField.Omitted,
    val notes: PatchField<String> = PatchField.Omitted,
    val highRisk: PatchField<Boolean> = PatchField.Omitted,
    val ncdFlags: PatchField<List<String>> = PatchField.Omitted,
    val ancHighRiskReasons: PatchField<List<String>> = PatchField.Omitted,
    val rchNumber: PatchField<String> = PatchField.Omitted,
    val rchBypass: PatchField<Boolean> = PatchField.Omitted,
    val lmp: PatchField<String> = PatchField.Omitted,
    val edd: PatchField<String> = PatchField.Omitted,
    val usgEdd: PatchField<String> = PatchField.Omitted,
    val surgicalPathway: PatchField<String> = PatchField.Omitted,
    val surgeryDone: PatchField<Boolean> = PatchField.Omitted,
    val surgeryDate: PatchField<String> = PatchField.Omitted,
    val reviewFrequency: PatchField<String> = PatchField.Omitted,
    val reviewDate: PatchField<String> = PatchField.Omitted,
    val gravida: PatchField<Int> = PatchField.Omitted,
    val para: PatchField<Int> = PatchField.Omitted,
    val abortions: PatchField<Int> = PatchField.Omitted,
    val living: PatchField<Int> = PatchField.Omitted,
    val ftnd: PatchField<Int> = PatchField.Omitted,
    val lscs: PatchField<Int> = PatchField.Omitted,
    val clientWriteId: PatchField<String> = PatchField.Omitted,
)

data class CaseCreateResponseDto(
    val message: String,
    @Json(name = "case_id") val caseId: Long,
    val case: CaseSummaryDto,
    @Json(name = "editable_case") val editableCase: CaseEditCaseDto? = null,
)

data class CaseUpdateResponseDto(
    val message: String,
    @Json(name = "case_id") val caseId: Long,
    val case: CaseSummaryDto,
    @Json(name = "editable_case") val editableCase: CaseEditCaseDto,
)

data class CaseCreateErrorDto(
    val message: String? = null,
    val errors: Map<String, List<String>> = emptyMap(),
)

data class CaseEditFormDto(
    @Json(name = "can_edit") val canEdit: Boolean = false,
    val categories: List<CaseCategoryDto> = emptyList(),
    val prefixes: List<ChoiceDto> = emptyList(),
    @Json(name = "blood_groups") val bloodGroups: List<ChoiceDto> = emptyList(),
    val genders: List<ChoiceDto> = emptyList(),
    @Json(name = "ncd_flags") val ncdFlags: List<ChoiceDto> = emptyList(),
    @Json(name = "anc_high_risk_reasons") val ancHighRiskReasons: List<ChoiceDto> = emptyList(),
    @Json(name = "surgical_pathways") val surgicalPathways: List<ChoiceDto> = emptyList(),
    @Json(name = "review_frequencies") val reviewFrequencies: List<ChoiceDto> = emptyList(),
    val case: CaseEditCaseDto,
)

data class CaseEditCaseDto(
    val id: Long,
    @Json(name = "base_updated_at") val baseUpdatedAt: String,
    @Json(name = "patient_mode") val patientMode: String? = null,
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
    val category: Long? = null,
    val subcategory: String? = null,
    val status: String? = null,
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
    @Json(name = "surgery_done") val surgeryDone: Boolean,
    @Json(name = "surgery_date") val surgeryDate: String? = null,
    @Json(name = "review_frequency") val reviewFrequency: String? = null,
    @Json(name = "review_date") val reviewDate: String? = null,
    val gravida: Int? = null,
    val para: Int? = null,
    val abortions: Int? = null,
    val living: Int? = null,
    val ftnd: Int? = null,
    val lscs: Int? = null,
)

data class TaskFormMetadataDto(
    @Json(name = "can_create") val canCreate: Boolean = false,
    @Json(name = "can_edit") val canEdit: Boolean = false,
    @Json(name = "can_reopen") val canReopen: Boolean = false,
    @Json(name = "default_status") val defaultStatus: String = "SCHEDULED",
    @Json(name = "task_types") val taskTypes: List<ChoiceDto> = emptyList(),
    val statuses: List<ChoiceDto> = emptyList(),
    @Json(name = "assignable_users") val assignableUsers: List<TaskAssigneeDto> = emptyList(),
)

data class TaskAssigneeDto(
    val id: Long,
    val name: String,
)

data class CreateTaskRequestDto(
    val title: String,
    @Json(name = "due_date") val dueDate: String,
    val status: String,
    @Json(name = "task_type") val taskType: String,
    @Json(name = "assigned_user") val assignedUser: Long? = null,
    val notes: String? = null,
    @Json(name = "client_write_id") val clientWriteId: String,
)

data class UpdateTaskRequestDto(
    val baseUpdatedAt: String,
    val baseValues: Map<String, Any?>,
    val title: PatchField<String> = PatchField.Omitted,
    val dueDate: PatchField<String> = PatchField.Omitted,
    val status: PatchField<String> = PatchField.Omitted,
    val taskType: PatchField<String> = PatchField.Omitted,
    val assignedUser: PatchField<Long> = PatchField.Omitted,
    val clientWriteId: String,
)

data class TaskNoteRequestDto(
    val note: String,
)

data class VitalsUpdateRequestDto(
    val baseUpdatedAt: String,
    val baseValues: Map<String, Any?>,
    val recordedAt: PatchField<String> = PatchField.Omitted,
    val bpSystolic: PatchField<Int> = PatchField.Omitted,
    val bpDiastolic: PatchField<Int> = PatchField.Omitted,
    val pr: PatchField<Int> = PatchField.Omitted,
    val spo2: PatchField<Int> = PatchField.Omitted,
    val weightKg: PatchField<String> = PatchField.Omitted,
    val hemoglobin: PatchField<String> = PatchField.Omitted,
    val clientWriteId: String,
)
