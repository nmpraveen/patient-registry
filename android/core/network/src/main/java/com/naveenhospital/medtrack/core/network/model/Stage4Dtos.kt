package com.naveenhospital.medtrack.core.network.model

import com.squareup.moshi.Json

data class UpcomingTaskDto(
    val id: Long,
    @Json(name = "case_id") val caseId: Long,
    @Json(name = "patient_name") val patientName: String,
    val department: String, val title: String,
    @Json(name = "due_date") val dueDate: String,
    @Json(name = "assigned_user_id") val assignedUserId: Long? = null,
    @Json(name = "assigned_user_name") val assignedUserName: String = "",
)
data class UpcomingPageDto(
    @Json(name = "hospital_today") val hospitalToday: String,
    @Json(name = "start_date") val startDate: String,
    @Json(name = "end_date") val endDate: String,
    val timezone: String, val results: List<UpcomingTaskDto>,
    @Json(name = "next_cursor") val nextCursor: String? = null,
)
data class CaseTimelineEventDto(
    val id: String,
    @Json(name = "event_type") val eventType: String,
    @Json(name = "event_label") val eventLabel: String,
    val timestamp: String, val actor: String = "",
    @Json(name = "task_title") val taskTitle: String = "",
    val headline: String, val reason: String = "", val details: String = "",
)
data class CaseTimelinePageDto(
    val results: List<CaseTimelineEventDto>,
    @Json(name = "next_cursor") val nextCursor: String? = null,
    val timezone: String,
)

data class UpcomingSearchRequestDto(
    val query: String,
    @Json(name = "start_date") val startDate: String? = null,
    val cursor: String? = null,
    val category: List<String> = emptyList(),
    val subcategory: List<String> = emptyList(),
    @Json(name = "assigned_to") val assignedTo: String? = null,
    @Json(name = "scope_context") val scopeContext: String? = null,
)

data class RelatedCaseDto(val id: Long, val department: String, val diagnosis: String, val status: String)
data class RelatedCasePageDto(
    val results: List<RelatedCaseDto>,
    @Json(name = "next_cursor") val nextCursor: String? = null,
)
