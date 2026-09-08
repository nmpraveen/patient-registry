package com.naveenhospital.medtrack.feature.cases

import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import com.naveenhospital.medtrack.core.domain.model.CaseFormCategory
import com.naveenhospital.medtrack.core.domain.model.CaseFormMetadata
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

class CaseIdentityFormTest {
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
