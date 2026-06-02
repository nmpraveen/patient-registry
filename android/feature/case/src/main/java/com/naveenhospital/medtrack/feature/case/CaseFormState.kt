package com.naveenhospital.medtrack.feature.cases

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import com.naveenhospital.medtrack.core.domain.model.CaseFormCategory
import com.naveenhospital.medtrack.core.domain.model.CaseFormMetadata
import com.naveenhospital.medtrack.core.domain.model.NewCaseInput
import com.naveenhospital.medtrack.core.domain.model.PatientLookup

/** Mutable holder for the multi-step case-creation wizard. */
class CaseFormState(
    val metadata: CaseFormMetadata,
    initialCategory: CaseCategory,
) {
    // Patient (new)
    var patientMode by mutableStateOf("new")
    var useTemporaryUhid by mutableStateOf(true)
    var uhid by mutableStateOf("")
    var prefix by mutableStateOf("")
    var firstName by mutableStateOf("")
    var lastName by mutableStateOf("")
    var gender by mutableStateOf("")
    var bloodGroup by mutableStateOf("")
    var age by mutableStateOf("")
    var phone by mutableStateOf("")
    var place by mutableStateOf("")

    // Patient (existing)
    var patientQuery by mutableStateOf("")
    var patientResults by mutableStateOf<List<PatientLookup>>(emptyList())
    var searching by mutableStateOf(false)
    var selectedPatient by mutableStateOf<PatientLookup?>(null)
    var searchPatients: suspend (String) -> List<PatientLookup> = { emptyList() }

    // Clinical
    var category by mutableStateOf<CaseFormCategory?>(null)
    var subcategory by mutableStateOf("")
    var diagnosis by mutableStateOf("")
    var referredBy by mutableStateOf("")
    var notes by mutableStateOf("")
    var highRisk by mutableStateOf(false)
    var ncdFlags by mutableStateOf<Set<String>>(emptySet())

    // ANC
    var gravida by mutableStateOf<Int?>(null)
    var para by mutableStateOf<Int?>(null)
    var abortions by mutableStateOf<Int?>(null)
    var living by mutableStateOf<Int?>(null)
    var ftnd by mutableStateOf<Int?>(null)
    var lscs by mutableStateOf<Int?>(null)
    var lmp by mutableStateOf("")
    var edd by mutableStateOf("")
    var usgEdd by mutableStateOf("")
    var rchNumber by mutableStateOf("")
    var rchBypass by mutableStateOf(true)
    var ancReasons by mutableStateOf<Set<String>>(emptySet())

    // Surgery
    var surgicalPathway by mutableStateOf("")
    var surgeryDate by mutableStateOf("")

    // Medicine
    var reviewFrequency by mutableStateOf("")
    var reviewDate by mutableStateOf("")

    init {
        val targetName = when (initialCategory) {
            CaseCategory.ANC -> "ANC"
            CaseCategory.SURGERY -> "Surgery"
            CaseCategory.MEDICINE -> "Medicine"
            else -> null
        }
        val initial = metadata.categories.firstOrNull { it.name.equals(targetName, ignoreCase = true) }
            ?: metadata.categories.firstOrNull()
        initial?.let { selectCategory(it) }
    }

    private fun CaseFormCategory.isAnc() = name.trim().equals("ANC", ignoreCase = true)
    private fun CaseFormCategory.isSurgery() = name.trim().equals("Surgery", ignoreCase = true)

    fun selectCategory(option: CaseFormCategory) {
        category = option
        subcategory = ""
        if (option.isAnc() && gender.isBlank()) gender = "FEMALE"
    }

    fun selectPatient(patient: PatientLookup) {
        selectedPatient = patient
        patientResults = emptyList()
        patientQuery = patient.name
    }

    fun toggleNcd(value: String) {
        ncdFlags = if (value in ncdFlags) ncdFlags - value else ncdFlags + value
    }

    fun toggleAncReason(value: String) {
        ancReasons = if (value in ancReasons) ancReasons - value else ancReasons + value
    }

    fun stepTitles(): List<String> {
        val pathway = category?.let {
            when {
                it.isAnc() -> "ANC"
                it.isSurgery() -> "Surgery"
                else -> "Medicine"
            }
        } ?: "Medicine"
        return listOf("Patient", "Clinical", pathway, "Review")
    }

    fun validateStep(title: String): String? {
        val cat = category
        return when (title) {
            "Patient" -> when {
                patientMode == "existing" && selectedPatient == null -> "Choose an existing patient."
                patientMode == "new" && firstName.isBlank() -> "Enter the patient's first name."
                patientMode == "new" && lastName.isBlank() -> "Enter the patient's last name."
                patientMode == "new" && prefix.isBlank() -> "Choose a prefix."
                patientMode == "new" && gender.isBlank() -> "Choose a sex."
                patientMode == "new" && age.toIntOrNull() == null -> "Enter a valid age."
                patientMode == "new" && phone.length != 10 -> "Enter a 10-digit phone number."
                patientMode == "new" && !useTemporaryUhid && uhid.isBlank() -> "Enter a UHID or use a temporary ID."
                else -> null
            }
            "Clinical" -> when {
                cat == null -> "Choose a category."
                cat.subcategories.isNotEmpty() && subcategory.isBlank() -> "Choose a subcategory."
                diagnosis.isBlank() -> "Enter a diagnosis or reason."
                else -> null
            }
            "ANC" -> when {
                lmp.isBlank() -> "Enter the LMP date."
                edd.isBlank() && usgEdd.isBlank() -> "Enter an EDD (LMP-based or USG)."
                !rchBypass && rchNumber.isBlank() -> "Enter an RCH number or bypass it."
                highRisk && ancReasons.isEmpty() -> "Select at least one high-risk reason."
                else -> null
            }
            "Surgery" -> when {
                surgicalPathway.isBlank() -> "Choose a surgical pathway."
                surgicalPathway == "PLANNED_SURGERY" && surgeryDate.isBlank() -> "Enter the surgery date."
                surgicalPathway == "SURVEILLANCE" && reviewDate.isBlank() -> "Enter the review date."
                else -> null
            }
            "Medicine" -> when {
                reviewDate.isBlank() -> "Enter a review date."
                else -> null
            }
            else -> null
        }
    }

    fun reviewPatientLine(): String {
        return if (patientMode == "existing") {
            selectedPatient?.let { "${it.name}  •  ${it.uhid}" } ?: "-"
        } else {
            val name = listOf(prefix, firstName, lastName).filter { it.isNotBlank() }.joinToString(" ")
            val suffix = age.toIntOrNull()?.let { "  •  ${it}y" } ?: ""
            (name.ifBlank { "New patient" }) + suffix
        }
    }

    fun subcategoryLabel(): String? =
        category?.subcategories?.firstOrNull { it.value == subcategory }?.label

    fun pathwaySummary(): String? {
        val cat = category ?: return null
        return when {
            cat.isAnc() -> "LMP ${lmp.ifBlank { "-" }}" + (if (edd.isNotBlank()) "  •  EDD $edd" else "")
            cat.isSurgery() -> {
                val label = metadata.surgicalPathways.firstOrNull { it.value == surgicalPathway }?.label ?: "-"
                if (surgeryDate.isNotBlank()) "$label  •  $surgeryDate" else label
            }
            else -> "Review ${reviewDate.ifBlank { "-" }}"
        }
    }

    fun toInput(): NewCaseInput {
        val cat = category!!
        val isAncCat = cat.isAnc()
        return NewCaseInput(
            patientMode = patientMode,
            selectedPatientId = if (patientMode == "existing") selectedPatient?.id else null,
            useTemporaryUhid = patientMode == "new" && useTemporaryUhid,
            uhid = uhid.ifBlank { null },
            prefix = prefix.ifBlank { null },
            firstName = firstName.ifBlank { null },
            lastName = lastName.ifBlank { null },
            gender = gender.ifBlank { null },
            bloodGroup = bloodGroup.ifBlank { null },
            place = place.ifBlank { null },
            age = age.toIntOrNull(),
            phoneNumber = phone.ifBlank { null },
            categoryId = cat.id,
            categoryName = cat.name,
            subcategory = subcategory.ifBlank { null },
            diagnosis = diagnosis.ifBlank { null },
            referredBy = referredBy.ifBlank { null },
            notes = notes.ifBlank { null },
            highRisk = highRisk,
            ncdFlags = ncdFlags.toList(),
            ancHighRiskReasons = if (isAncCat && highRisk) ancReasons.toList() else emptyList(),
            rchNumber = if (isAncCat) rchNumber.ifBlank { null } else null,
            rchBypass = isAncCat && rchBypass,
            lmp = if (isAncCat) lmp.ifBlank { null } else null,
            edd = if (isAncCat) edd.ifBlank { null } else null,
            usgEdd = if (isAncCat) usgEdd.ifBlank { null } else null,
            surgicalPathway = surgicalPathway.ifBlank { null },
            surgeryDate = surgeryDate.ifBlank { null },
            reviewFrequency = reviewFrequency.ifBlank { null },
            reviewDate = reviewDate.ifBlank { null },
            gravida = gravida,
            para = para,
            abortions = abortions,
            living = living,
            ftnd = ftnd,
            lscs = lscs,
        )
    }
}
