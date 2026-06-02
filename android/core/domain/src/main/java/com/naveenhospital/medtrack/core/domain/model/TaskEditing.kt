package com.naveenhospital.medtrack.core.domain.model

/** Menus + permissions for the mobile task create/edit sheet, driven by the server. */
data class TaskFormMetadata(
    val canCreate: Boolean,
    val canEdit: Boolean,
    val canReopen: Boolean,
    val defaultStatus: String,
    val taskTypes: List<FormChoice>,
    val statuses: List<FormChoice>,
    val assignableUsers: List<TaskAssignee>,
)

data class TaskAssignee(
    val id: Long,
    val name: String,
)

/** Payload for creating a task (mirrors the web TaskForm field set). */
data class NewTaskInput(
    val title: String,
    val dueDate: String,
    val status: String,
    val taskType: String,
    val assignedUserId: Long? = null,
    val notes: String? = null,
)

/** Partial edit payload — only non-null fields are sent. */
data class TaskEditInput(
    val title: String? = null,
    val dueDate: String? = null,
    val status: String? = null,
    val taskType: String? = null,
    val assignedUserId: Long? = null,
    val clearAssignee: Boolean = false,
)

/** Raw editable case fields used to seed the case-edit wizard. */
data class CaseEditPrefill(
    val canEdit: Boolean,
    val metadata: CaseFormMetadata,
    val patientMode: String,
    val selectedPatientId: Long?,
    val useTemporaryUhid: Boolean,
    val uhid: String?,
    val prefix: String?,
    val firstName: String?,
    val lastName: String?,
    val gender: String?,
    val bloodGroup: String?,
    val place: String?,
    val age: Int?,
    val phoneNumber: String?,
    val categoryId: Long?,
    val subcategory: String?,
    val status: String?,
    val diagnosis: String?,
    val referredBy: String?,
    val notes: String?,
    val highRisk: Boolean,
    val ncdFlags: List<String>,
    val ancHighRiskReasons: List<String>,
    val rchNumber: String?,
    val rchBypass: Boolean,
    val lmp: String?,
    val edd: String?,
    val usgEdd: String?,
    val surgicalPathway: String?,
    val surgeryDate: String?,
    val reviewFrequency: String?,
    val reviewDate: String?,
    val gravida: Int?,
    val para: Int?,
    val abortions: Int?,
    val living: Int?,
    val ftnd: Int?,
    val lscs: Int?,
)

sealed interface CaseEditOutcome {
    data class Success(val caseId: Long, val message: String) : CaseEditOutcome

    data class ValidationError(
        val errors: Map<String, List<String>>,
        val message: String,
    ) : CaseEditOutcome

    data class Failure(val message: String) : CaseEditOutcome
}

sealed interface TaskWriteOutcome {
    data class Success(val message: String) : TaskWriteOutcome

    data class ValidationError(
        val errors: Map<String, List<String>>,
        val message: String,
    ) : TaskWriteOutcome

    data class Failure(val message: String) : TaskWriteOutcome
}

sealed interface VitalsWriteOutcome {
    data class Success(val message: String) : VitalsWriteOutcome

    data class ValidationError(
        val errors: Map<String, List<String>>,
        val message: String,
    ) : VitalsWriteOutcome

    data class Failure(val message: String) : VitalsWriteOutcome
}
