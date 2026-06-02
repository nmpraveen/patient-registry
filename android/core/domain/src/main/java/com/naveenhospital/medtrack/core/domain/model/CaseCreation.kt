package com.naveenhospital.medtrack.core.domain.model

/** A single selectable option (server value + human label) for a form menu. */
data class FormChoice(
    val value: String,
    val label: String,
)

data class CaseFormCategory(
    val id: Long,
    val name: String,
    val subcategories: List<FormChoice>,
)

/** Everything the case-creation wizard needs to render its menus, driven by the server. */
data class CaseFormMetadata(
    val canCreate: Boolean,
    val categories: List<CaseFormCategory>,
    val prefixes: List<FormChoice>,
    val bloodGroups: List<FormChoice>,
    val genders: List<FormChoice>,
    val ncdFlags: List<FormChoice>,
    val ancHighRiskReasons: List<FormChoice>,
    val surgicalPathways: List<FormChoice>,
    val reviewFrequencies: List<FormChoice>,
)

data class PatientLookup(
    val id: Long,
    val uhid: String,
    val name: String,
    val prefix: String,
    val firstName: String,
    val lastName: String,
    val gender: String,
    val genderLabel: String,
    val bloodGroup: String,
    val dateOfBirth: String?,
    val age: Int?,
    val place: String,
    val phoneNumber: String,
    val alternatePhoneNumber: String,
    val isTemporaryId: Boolean,
    val activeCaseCount: Int?,
)

/** Form payload mirroring the web CaseForm field set. */
data class NewCaseInput(
    val patientMode: String,
    val selectedPatientId: Long? = null,
    val useTemporaryUhid: Boolean = false,
    val uhid: String? = null,
    val prefix: String? = null,
    val firstName: String? = null,
    val lastName: String? = null,
    val gender: String? = null,
    val bloodGroup: String? = null,
    val dateOfBirth: String? = null,
    val place: String? = null,
    val age: Int? = null,
    val phoneNumber: String? = null,
    val alternatePhoneNumber: String? = null,
    val categoryId: Long,
    val categoryName: String,
    val subcategory: String? = null,
    val diagnosis: String? = null,
    val referredBy: String? = null,
    val notes: String? = null,
    val highRisk: Boolean = false,
    val ncdFlags: List<String> = emptyList(),
    val ancHighRiskReasons: List<String> = emptyList(),
    val rchNumber: String? = null,
    val rchBypass: Boolean = false,
    val lmp: String? = null,
    val edd: String? = null,
    val usgEdd: String? = null,
    val surgicalPathway: String? = null,
    val surgeryDate: String? = null,
    val reviewFrequency: String? = null,
    val reviewDate: String? = null,
    val gravida: Int? = null,
    val para: Int? = null,
    val abortions: Int? = null,
    val living: Int? = null,
    val ftnd: Int? = null,
    val lscs: Int? = null,
)

sealed interface CaseCreateOutcome {
    data class Success(val caseId: Long, val message: String) : CaseCreateOutcome

    data class ValidationError(
        val errors: Map<String, List<String>>,
        val message: String,
    ) : CaseCreateOutcome

    data class Failure(val message: String) : CaseCreateOutcome
}
