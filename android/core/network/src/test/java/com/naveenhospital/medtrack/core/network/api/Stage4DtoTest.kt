package com.naveenhospital.medtrack.core.network.api

import com.naveenhospital.medtrack.core.network.model.*
import org.junit.Assert.*
import org.junit.Test

class Stage4DtoTest {
    private val moshi = MedtrackNetwork.contractMoshi()

    @Test fun timelineRetainsCanonicalIdsMicrosecondPrecisionAndCursor() {
        val json = """{"results":[{"id":"call:7","event_type":"CALL","event_label":"Call","timestamp":"2026-09-08T00:00:00.123456+05:30","actor":"Staff","task_title":"","headline":"Reached","reason":"Follow up","details":""}],"next_cursor":"opaque:next","timezone":"Asia/Kolkata"}"""
        val page = moshi.adapter(CaseTimelinePageDto::class.java).fromJson(json)!!
        assertEquals("call:7", page.results.single().id)
        assertEquals("2026-09-08T00:00:00.123456+05:30", page.results.single().timestamp)
        assertEquals("opaque:next", page.nextCursor)
        assertEquals("Follow up", page.results.single().reason)
    }

    @Test fun upcomingKeepsDateAndUnassignedTaskWithoutCoercion() {
        val json = """{"hospital_today":"2026-12-31","start_date":"2026-12-31","end_date":"2027-01-06","timezone":"Asia/Kolkata","results":[{"id":4,"case_id":2,"patient_name":"Synthetic","department":"Medicine","title":"Review","due_date":"2027-01-01","assigned_user_id":null,"assigned_user_name":""}],"next_cursor":null}"""
        val page = moshi.adapter(UpcomingPageDto::class.java).fromJson(json)!!
        assertEquals("2027-01-01", page.results.single().dueDate)
        assertNull(page.results.single().assignedUserId)
        assertNull(page.nextCursor)
    }

    @Test fun privateSearchAndFiltersEncodeInPostBody() {
        val request = UpcomingSearchRequestDto("Synthetic", "2026-09-08", "opaque", listOf("Medicine"), listOf("Review"), "me")
        val json = moshi.adapter(UpcomingSearchRequestDto::class.java).toJson(request)
        val map = moshi.adapter(Any::class.java).fromJson(json) as Map<*, *>
        assertEquals("Synthetic", map["query"])
        assertEquals("2026-09-08", map["start_date"])
        assertEquals(listOf("Medicine"), map["category"])
        assertEquals("me", map["assigned_to"])
    }
}
