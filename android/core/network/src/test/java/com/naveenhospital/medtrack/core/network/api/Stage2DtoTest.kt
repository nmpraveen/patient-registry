package com.naveenhospital.medtrack.core.network.api

import com.naveenhospital.medtrack.core.network.model.*
import org.junit.Assert.*
import org.junit.Test

class Stage2DtoTest {
    private val moshi = MedtrackNetwork.contractMoshi()
    private fun value(json: String) = moshi.adapter(Any::class.java).fromJson(json)

    @Test fun legacyCallAndCompletionReencodeWithoutNewKeys() {
        val call = """{"outcome":"attempted","note":"Original note","client_write_id":"old-call","attempted_at":"2026-01-01T00:00:00Z"}"""
        val adapter = moshi.adapter(LogCallRequestDto::class.java)
        assertEquals(value(call), value(adapter.toJson(adapter.fromJson(call))))
        val completion = """{"client_write_id":"old-completion"}"""
        val completeAdapter = moshi.adapter(ClientWriteRequestDto::class.java)
        assertEquals(value(completion), value(completeAdapter.toJson(completeAdapter.fromJson(completion))))
    }

    @Test fun newControlsAndReasonsRoundTrip() {
        val call = LogCallRequestDto(outcome = "reached", reason = "Clarify appointment", clientWriteId = "call-2")
        val adapter = moshi.adapter(LogCallRequestDto::class.java)
        assertEquals(call, adapter.fromJson(adapter.toJson(call)))
        val complete = ClientWriteRequestDto("complete-2", mapOf("status" to "SCHEDULED", "due_date" to "2026-09-08"))
        val completeAdapter = moshi.adapter(ClientWriteRequestDto::class.java)
        assertEquals(complete, completeAdapter.fromJson(completeAdapter.toJson(complete)))
    }

    @Test fun fullTaskPatchPreservesOmissionAndBlankClears() {
        val adapter = moshi.adapter(UpdateTaskRequestDto::class.java)
        val json = adapter.toJson(UpdateTaskRequestDto(
            baseUpdatedAt = "2026-09-07T00:00:00Z", baseValues = mapOf("notes" to "Original", "frequency_label" to "Monthly"),
            notes = PatchField.Value(""), frequencyLabel = PatchField.Value("Weekly"), clientWriteId = "edit-1",
        ))
        val map = value(json) as Map<*, *>
        assertEquals("", map["notes"])
        assertEquals("Weekly", map["frequency_label"])
        assertFalse(map.containsKey("assigned_user"))
        assertFalse(map.containsKey("due_date"))
    }

    @Test fun olderCallResponseDefaultsRemainHonest() {
        val call = moshi.adapter(CallLogDto::class.java).fromJson("""{"id":1,"task_id":null,"outcome":"REACHED","outcome_label":"Reached","notes":"","created_at":"2026-09-07T00:00:00Z"}""")!!
        assertEquals("", call.reason)
        assertEquals("", call.taskTitle)
        assertEquals("", call.staffUser)
        assertNull(call.clientEventAt)
    }
}
