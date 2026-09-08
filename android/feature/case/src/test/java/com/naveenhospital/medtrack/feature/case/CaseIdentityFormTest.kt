package com.naveenhospital.medtrack.feature.cases

import com.naveenhospital.medtrack.core.domain.model.PatientCase
import com.naveenhospital.medtrack.core.domain.model.CaseStatus
import com.naveenhospital.medtrack.core.domain.model.CaseEditPrefill
import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import com.naveenhospital.medtrack.core.domain.model.CaseFormCategory
import com.naveenhospital.medtrack.core.domain.model.CaseFormMetadata
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CaseIdentityFormTest {
    @Test
    fun identitySearchAndGroupingNeverMergeBlankIdsByDemographics() {
        val case = PatientCase(id = "42", uhid = "", patientName = "Synthetic Record",
            category = CaseCategory.MEDICINE, status = CaseStatus.ACTIVE, diagnosis = "Review", isHighRisk = false)
        assertNotEquals(case.dedupeKey(), case.copy(id = "43").dedupeKey())
        val identified = case.copy(mtno = "MT-000042", uhid = "HOSP-0042")
        assertEquals(identified.dedupeKey(), identified.copy(id = "43").dedupeKey())
        assertTrue(identified.matchesCaseSearch("mt-000042"))
        assertTrue(identified.matchesCaseSearch("hosp-0042"))
        assertFalse(identified.matchesCaseSearch("MT-000043"))
        assertTrue(case.copy(uhid = "TMP-LEGACY").matchesCaseSearch("tmp-legacy"))
    }

    @Test
    fun laterHospitalIdAssignmentRetainsMtnoAndUnchangedLegacyTmpFlag() {
        val metadata = CaseFormMetadata(true, listOf(CaseFormCategory(2, "Medicine", emptyList())),
            emptyList(), emptyList(), emptyList(), emptyList(), emptyList(), emptyList(), emptyList())
        val state = CaseFormState(metadata, CaseCategory.MEDICINE)
        val prefill = CaseEditPrefill(
            mtno = "MT-000042", canEdit = true, metadata = metadata, patientMode = "existing",
            selectedPatientId = 9, useTemporaryUhid = true, uhid = "TMP-LEGACY", prefix = "Ms",
            firstName = "Synthetic", lastName = "Record", gender = "FEMALE", bloodGroup = null,
            dateOfBirth = null, place = null, age = 30, phoneNumber = "9000000042", alternatePhoneNumber = null,
            categoryId = 2, subcategory = null, status = "ACTIVE", diagnosis = null, referredBy = null,
            notes = null, highRisk = false, ncdFlags = emptyList(), ancHighRiskReasons = emptyList(),
            rchNumber = null, rchBypass = false, lmp = null, edd = null, usgEdd = null,
            surgicalPathway = null, surgeryDone = false, surgeryDate = null, reviewFrequency = null,
            reviewDate = null, gravida = null, para = null, abortions = null, living = null, ftnd = null, lscs = null,
        )
        state.applyPrefill(prefill)
        assertEquals("MT-000042", state.mtno)
        state.diagnosis = "Updated review"
        assertEquals("TMP-LEGACY", state.toInput().uhid)
        assertTrue(state.toInput().useTemporaryUhid)
        state.uhid = "HOSP-0042"
        assertFalse(state.toInput().useTemporaryUhid)
        assertEquals("MT-000042", state.mtno)
        state.applyPrefill(prefill.copy(uhid = "", useTemporaryUhid = false))
        assertNull(state.validateStep("Patient"))
        state.uhid = "HOSP-0042"
        assertEquals("HOSP-0042", state.toInput().uhid)
        assertEquals("MT-000042", state.mtno)
    }

    @Test
    fun registrationAllowsMissingHospitalIdWithoutTemporaryAllocation() {
        val metadata = CaseFormMetadata(true, listOf(CaseFormCategory(2, "Medicine", emptyList())),
            emptyList(), emptyList(), emptyList(), emptyList(), emptyList(), emptyList(), emptyList())
        val state = CaseFormState(metadata, CaseCategory.MEDICINE).apply {
            prefix = "Ms"
            firstName = "Synthetic"
            lastName = "Record"
            gender = "FEMALE"
            age = "30"
            phone = "9000000042"
        }
        assertNull(state.validateStep("Patient"))
        assertFalse(state.toInput().useTemporaryUhid)
        assertNull(state.toInput().uhid)
        assertEquals("", state.mtno)
        state.uhid = "UH-0042"
        assertEquals("UH-0042", state.toInput().uhid)
        assertEquals("", state.mtno)
    }
}
