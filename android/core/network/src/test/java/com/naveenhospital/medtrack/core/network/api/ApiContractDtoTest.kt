package com.naveenhospital.medtrack.core.network.api

import com.naveenhospital.medtrack.core.network.model.CaseEditFormDto
import com.naveenhospital.medtrack.core.network.model.CaseSearchRequestDto
import com.naveenhospital.medtrack.core.network.model.CaseSearchResponseDto
import com.naveenhospital.medtrack.core.network.model.CaseUpdateResponseDto
import com.naveenhospital.medtrack.core.network.model.NotificationsResponseDto
import com.naveenhospital.medtrack.core.network.model.PatientSearchRequestDto
import com.naveenhospital.medtrack.core.network.model.PatientSearchResponseDto
import com.naveenhospital.medtrack.core.network.model.PatchField
import com.naveenhospital.medtrack.core.network.model.UpdateCaseRequestDto
import com.naveenhospital.medtrack.core.network.model.UpdateTaskRequestDto
import com.naveenhospital.medtrack.core.network.model.VitalsUpdateRequestDto
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

class ApiContractDtoTest {
    private val moshi = MedtrackNetwork.contractMoshi()

    @Test
    fun mtnoIsAdditiveAcrossSearchDetailAndEditWithBlankUhid() {
        val cases = moshi.adapter(CaseSearchResponseDto::class.java)
        val patients = moshi.adapter(PatientSearchResponseDto::class.java)
        val edit = moshi.adapter(CaseEditFormDto::class.java)
        assertEquals("", cases.fromJson(CASE_SEARCH_PAGE)!!.results.single().mtno)
        assertEquals("", patients.fromJson(PATIENT_SEARCH_PAGE)!!.results.single().mtno)
        assertEquals("", edit.fromJson(CURRENT_CASE_EDIT_RESPONSE)!!.case.mtno)
        fun identified(json: String) = json.replace("\"uhid\": \"TEST-0001\"", "\"uhid\": \"\", \"mtno\": \"MT-000042\"")
        val summary = cases.fromJson(identified(CASE_SEARCH_PAGE))!!.results.single()
        assertEquals("MT-000042", summary.mtno)
        assertEquals("", summary.uhid)
        assertEquals("MT-000042", patients.fromJson(identified(PATIENT_SEARCH_PAGE))!!.results.single().mtno)
        assertEquals("MT-000042", edit.fromJson(identified(CURRENT_CASE_EDIT_RESPONSE))!!.case.mtno)
        val detail = moshi.adapter(com.naveenhospital.medtrack.core.network.model.CaseDetailDto::class.java)
            .fromJson("{\"case\":" + moshi.adapter(com.naveenhospital.medtrack.core.network.model.CaseSummaryDto::class.java).toJson(summary) + ",\"tasks\":[]}")!!
        assertEquals("MT-000042", detail.case.mtno)
    }

    @Test
    fun blankUhidAndLegacyTemporaryRequestsNeverSendMtno() {
        val adapter = moshi.adapter(com.naveenhospital.medtrack.core.network.model.CreateCaseRequestDto::class.java)
        val current = com.naveenhospital.medtrack.core.network.model.CreateCaseRequestDto(patientMode = "new", category = 2, uhid = "", clientWriteId = "blank-uhid")
        val currentJson = adapter.toJson(current)
        assertFalse(currentJson.contains("mtno"))
        assertFalse(adapter.fromJson(currentJson)!!.useTemporaryUhid)
        val legacy = adapter.fromJson("""{"patient_mode":"new","category":2,"use_temporary_uhid":true,"uhid":"TMP-LEGACY","client_write_id":"old-write"}""")!!
        assertTrue(legacy.useTemporaryUhid)
        assertEquals("TMP-LEGACY", legacy.uhid)
        assertEquals("old-write", legacy.clientWriteId)
        assertFalse(adapter.toJson(legacy).contains("mtno"))
    }

    @Test
    fun followUpFieldsAreAdditiveForOlderServersAndPreservedWhenPresent() {
        val adapter = moshi.adapter(CaseSearchResponseDto::class.java)
        val old = adapter.fromJson(CASE_SEARCH_PAGE)!!
        assertEquals(0, old.stats.dormant)
        assertNull(old.results.first().followUp)
        val enriched = CASE_SEARCH_PAGE.replace("\"red\": 1", "\"red\": 1, \"dormant\": 2")
            .replace("\"diagnosis\": \"Review\"", """"diagnosis": "Review", "updated_at": "2026-09-08T00:00:00Z",
                "follow_up": {"label": "Overdue — EDD", "edd_missing": false, "effective_edd": "2026-09-07",
                    "outcome_label": "Referral", "outcome_date": "2026-09-07", "reason": "Synthetic referral", "referral_destination": "Demo clinic"}""")
        val current = adapter.fromJson(enriched)!!
        assertEquals(2, current.stats.dormant)
        assertEquals("Overdue — EDD", current.results.first().followUp?.label)
        assertEquals("2026-09-07", current.results.first().followUp?.effectiveEdd)
        assertEquals("Demo clinic", current.results.first().followUp?.referralDestination)
        assertEquals("2026-09-08T00:00:00Z", current.results.first().updatedAt)
    }

    @Test
    fun caseEditContractRequiresCompleteEditableSnapshot() {
        val malformed = CURRENT_CASE_EDIT_RESPONSE.replace("\"surgery_done\": true,", "")

        assertTrue(runCatching { moshi.adapter(CaseEditFormDto::class.java).fromJson(malformed) }.isFailure)
    }

    @Test
    fun coordinatedCaseEditContractPreservesTrueSurgeryDoneInPatch() {
        val response = moshi.adapter(CaseEditFormDto::class.java).fromJson(CURRENT_CASE_EDIT_RESPONSE)
        val editableCase = requireNotNull(response?.case)
        val request = UpdateCaseRequestDto(
            baseUpdatedAt = editableCase.baseUpdatedAt,
            baseValues = mapOf("diagnosis" to "Review", "surgery_done" to true),
            diagnosis = PatchField.Value("Post-operative review"),
            surgeryDone = PatchField.Value(editableCase.surgeryDone),
            clientWriteId = PatchField.Value("contract-test-write"),
        )
        val json = moshi.adapter(UpdateCaseRequestDto::class.java).toJson(request)
        assertFalse(json.contains("mtno"))

        assertTrue(json.contains("\"surgery_done\":true"))
        assertTrue(json.contains("\"diagnosis\":\"Post-operative review\""))
        assertTrue(json.contains("\"base_updated_at\":\"2026-08-29T18:00:00Z\""))
        assertTrue(json.contains("\"base_values\""))
        assertFalse(json.contains("\"high_risk\""))
        assertFalse(json.contains("\"ncd_flags\""))
    }

    @Test
    fun casePatchDistinguishesOmissionFromExplicitNullClearing() {
        val request = UpdateCaseRequestDto(
            baseUpdatedAt = "2026-08-29T18:00:00Z",
            baseValues = mapOf("notes" to "old note"),
            notes = PatchField.Value(null),
            diagnosis = PatchField.Omitted,
            clientWriteId = PatchField.Value("contract-test-write"),
        )

        val json = moshi.adapter(UpdateCaseRequestDto::class.java).toJson(request)

        assertTrue(json.contains("\"notes\":null"))
        assertFalse(json.contains("\"diagnosis\""))
        assertTrue(json.contains("\"client_write_id\":\"contract-test-write\""))
    }

    @Test
    fun taskAndVitalPatchesCarryTouchedBaselinesAndExplicitNulls() {
        val taskJson = moshi.adapter(UpdateTaskRequestDto::class.java).toJson(
            UpdateTaskRequestDto(
                baseUpdatedAt = "2026-08-29T18:00:00Z",
                baseValues = mapOf("assigned_user" to 7L),
                assignedUser = PatchField.Value(null),
                clientWriteId = "task-write",
            ),
        )
        val vitalJson = moshi.adapter(VitalsUpdateRequestDto::class.java).toJson(
            VitalsUpdateRequestDto(
                baseUpdatedAt = "2026-08-29T18:00:00Z",
                baseValues = mapOf("spo2" to 97),
                spo2 = PatchField.Value(98),
                clientWriteId = "vital-write",
            ),
        )

        assertTrue(taskJson.contains("\"base_values\":{\"assigned_user\":7}"))
        assertTrue(taskJson.contains("\"assigned_user\":null"))
        assertFalse(taskJson.contains("\"status\""))
        assertTrue(vitalJson.contains("\"base_values\":{\"spo2\":97}"))
        assertTrue(vitalJson.contains("\"spo2\":98"))
        assertFalse(vitalJson.contains("\"bp_systolic\""))
    }

    @Test
    fun coordinatedPatchResponseReturnsAuthoritativeEditableCase() {
        val response = moshi.adapter(CaseUpdateResponseDto::class.java).fromJson(CASE_PATCH_RESPONSE)

        assertEquals(42L, response?.caseId)
        assertEquals(true, response?.editableCase?.surgeryDone)
        assertEquals("1990-01-02", response?.editableCase?.dateOfBirth)
        assertEquals("9000000001", response?.editableCase?.alternatePhoneNumber)
    }

    @Test
    fun notificationContractCarriesOpaqueCursorDatasetEpochAndEventIds() {
        val response = moshi.adapter(NotificationsResponseDto::class.java).fromJson(NOTIFICATIONS_PAGE)

        assertEquals("11111111-1111-4111-8111-111111111111", response?.datasetEpoch)
        assertEquals("opaque-next-cursor", response?.nextCursor)
        assertEquals(listOf(101L), response?.results?.map { it.id })
        assertEquals(listOf("22222222-2222-4222-8222-222222222222"), response?.results?.map { it.eventId })
    }

    @Test
    fun patientSearchContractUsesPhiMinimalPostBodyAndCursorResponse() {
        val request = PatientSearchRequestDto(
            query = "TEST-00",
            pageSize = 20,
            cursor = "opaque-search-cursor",
        )
        val requestJson = moshi.adapter(PatientSearchRequestDto::class.java).toJson(request)
        val response = moshi.adapter(PatientSearchResponseDto::class.java).fromJson(PATIENT_SEARCH_PAGE)
        val apiMethod = MedtrackApi::class.java.declaredMethods.single { it.name == "searchPatients" }
        val post = requireNotNull(apiMethod.getAnnotation(POST::class.java))

        assertEquals("api/patients/", post.value)
        assertTrue(apiMethod.parameterAnnotations.flatten().any { it is Body })
        assertFalse(apiMethod.parameterAnnotations.flatten().any { it is Query })
        assertTrue(requestJson.contains("\"query\":\"TEST-00\""))
        assertTrue(requestJson.contains("\"page_size\":20"))
        assertTrue(requestJson.contains("\"cursor\":\"opaque-search-cursor\""))
        assertEquals("opaque-search-next", response?.nextCursor)
        assertEquals(listOf("TEST-0001"), response?.results?.map { it.uhid })
        val encodedResponse = moshi.adapter(PatientSearchResponseDto::class.java).toJson(response)
        val responseObject = requireNotNull(moshi.adapter(Map::class.java).fromJson(encodedResponse))
        val resultObject = (responseObject["results"] as List<*>).single() as Map<*, *>
        assertEquals(setOf("next_cursor", "results"), responseObject.keys)
        assertEquals(setOf("id", "mtno", "uhid", "name"), resultObject.keys)
        assertFalse(
            MedtrackApi::class.java.declaredMethods.any { method ->
                method.getAnnotation(GET::class.java)?.value == "api/patients/"
            },
        )
    }

    @Test
    fun caseSearchContractUsesPostBodyCursorAndNeverGetQuery() {
        val request = CaseSearchRequestDto(
            query = "TEST-00",
            pageSize = 20,
            cursor = "opaque-case-cursor",
            bucket = "overdue",
            assignedTo = "me",
            scopeContext = "all",
            category = listOf("Surgery"),
            subcategory = listOf("Review"),
        )
        val requestJson = moshi.adapter(CaseSearchRequestDto::class.java).toJson(request)
        val response = moshi.adapter(CaseSearchResponseDto::class.java).fromJson(CASE_SEARCH_PAGE)
        val searchMethod = MedtrackApi::class.java.declaredMethods.single { it.name == "searchCases" }
        val listMethod = MedtrackApi::class.java.declaredMethods.single { it.name == "listCases" }

        assertEquals("api/cases/search/", requireNotNull(searchMethod.getAnnotation(POST::class.java)).value)
        assertTrue(searchMethod.parameterAnnotations.flatten().any { it is Body })
        assertFalse(searchMethod.parameterAnnotations.flatten().any { it is Query })
        assertFalse(listMethod.parameterAnnotations.flatten().filterIsInstance<Query>().any { it.value == "q" })
        assertTrue(requestJson.contains("\"query\":\"TEST-00\""))
        assertTrue(requestJson.contains("\"cursor\":\"opaque-case-cursor\""))
        assertEquals("opaque-case-next", response?.nextCursor)
        assertEquals(4, response?.stats?.overdue)
        assertEquals(listOf(42L), response?.results?.map { it.id })
    }

    @Test
    fun notificationRequestHasCursorAndNeverLegacyPageQuery() {
        val apiMethod = MedtrackApi::class.java.declaredMethods.single { it.name == "notifications" }
        val queryNames = apiMethod.parameterAnnotations
            .flatten()
            .filterIsInstance<Query>()
            .map { it.value }

        assertEquals(setOf("type", "unread_only", "cursor", "page_size"), queryNames.toSet())
        assertFalse("page" in queryNames)
    }

    @Test
    fun debugRequestLabelNeverContainsQueryValuesAndRedactsNumericIds() {
        val label = MedtrackNetwork.safeRequestLabel("GET", "/api/cases/123/")

        assertEquals("GET /api/cases/{id}/", label)
        assertFalse(label.contains("patient"))
        assertFalse(label.contains("?"))
    }

    private companion object {
        val CURRENT_CASE_EDIT_RESPONSE =
            """
            {
              "can_edit": true,
              "categories": [{"id": 2, "name": "Surgery", "subcategories": []}],
              "prefixes": [], "blood_groups": [], "genders": [], "ncd_flags": [],
              "anc_high_risk_reasons": [], "surgical_pathways": [], "review_frequencies": [],
              "case": {
                "id": 42, "base_updated_at": "2026-08-29T18:00:00Z",
                "surgery_done": true, "patient_mode": "existing", "selected_patient": 9,
                "use_temporary_uhid": false, "uhid": "TEST-0001", "first_name": "Test",
                "last_name": "Record", "category": 2, "status": "ACTIVE",
                "diagnosis": "Review", "high_risk": false, "ncd_flags": [],
                "anc_high_risk_reasons": [], "rch_bypass": false,
                "surgical_pathway":"PLANNED_SURGERY", "surgery_date": "2026-08-01"
              }
            }
            """.trimIndent()

        val NOTIFICATIONS_PAGE =
            """
            {
              "dataset_epoch": "11111111-1111-4111-8111-111111111111",
              "next_cursor": "opaque-next-cursor",
              "results": [{
                "id": 101, "event_id": "22222222-2222-4222-8222-222222222222", "type": "assignment",
                "title": "MEDTRACK update", "body": "Open MEDTRACK to review this update.",
                "case_id": 42, "task_id": null,
                "payload": {"event_id": "22222222-2222-4222-8222-222222222222", "type": "assignment", "channel": "assignments"},
                "read_at": null, "created_at": "2026-08-29T18:00:00Z"
              }]
            }
            """.trimIndent()

        val PATIENT_SEARCH_PAGE =
            """
            {
              "next_cursor": "opaque-search-next",
              "results": [{"id": 9, "uhid": "TEST-0001", "name": "Test Record"}]
            }
            """.trimIndent()

        val CASE_SEARCH_PAGE =
            """
            {
              "next_cursor": "opaque-case-next",
              "stats": {"today": 1, "upcoming": 2, "overdue": 4, "awaiting": 3, "red": 1},
              "results": [{
                "id": 42, "uhid": "TEST-0001", "name": "Test Record", "age": 36,
                "sex": "F", "sex_label": "Female", "place": "Test", "phone_number": "9000000000",
                "category": {"id": 2, "name": "Surgery", "subcategories": []},
                "subcategory": null, "status": "ACTIVE", "diagnosis": "Review",
                "red_flag": false, "red_flag_reasons": [], "next_task": null, "latest_vital": null
              }]
            }
            """.trimIndent()

        val CASE_PATCH_RESPONSE =
            """
            {
              "message": "Case updated.",
              "case_id": 42,
              "case": {
                "id": 42, "uhid": "TEST-0001", "name": "Test Record", "age": 36,
                "sex_label": "Female", "place": "Test", "phone_number": "9000000000",
                "category": {"id": 2, "name": "Surgery", "subcategory": null, "subcategories": []},
                "subcategory": null, "status": "ACTIVE", "status_label": "Active",
                "diagnosis": "Review", "red_flag": false, "red_flag_reasons": [],
                "next_task": null, "latest_vital": null,
                "search_text": "test record test-0001", "dedupe_key": "test-0001"
              },
              "editable_case": {
                "id": 42, "base_updated_at": "2026-08-29T18:05:00Z",
                "patient_mode": "existing", "selected_patient": 9,
                "uhid": "TEST-0001", "first_name": "Test", "last_name": "Record",
                "date_of_birth": "1990-01-02", "alternate_phone_number": "9000000001",
                "category": 2, "status": "ACTIVE", "diagnosis": "Review",
                "high_risk": false, "ncd_flags": [], "anc_high_risk_reasons": [],
                "rch_bypass": false, "surgical_pathway": "PLANNED_SURGERY",
                "surgery_done": true
              }
            }
            """.trimIndent()
    }
}
