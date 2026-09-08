package com.naveenhospital.medtrack.core.network.model

import com.squareup.moshi.Json

data class StaffPageDto<T>(
    val count: Int,
    val next: String? = null,
    val previous: String? = null,
    val results: List<T>,
    @Json(name = "server_now") val serverNow: String? = null,
    @Json(name = "server_today") val serverToday: String? = null,
)

data class DirectoryPhoneDto(val label: String = "", val number: String, val extension: String = "")
data class DirectoryContactDto(
    val id: Long,
    val name: String,
    @Json(name = "role_specialty") val roleSpecialty: String = "",
    val organization: String = "",
    val phones: List<DirectoryPhoneDto> = emptyList(),
    val notes: String = "",
    @Json(name = "is_active") val isActive: Boolean,
    @Json(name = "is_favourite") val isFavourite: Boolean,
    val version: Long,
)
data class FavouriteRequestDto(@Json(name = "is_favourite") val isFavourite: Boolean)
data class StaffPersonDto(val id: Long, val name: String)
data class StaffAnnouncementDto(
    val id: Long,
    val text: String,
    val priority: String,
    val audience: String,
    @Json(name = "starts_at") val startsAt: String,
    @Json(name = "ends_at") val endsAt: String,
    val publisher: StaffPersonDto,
    val version: Long,
    @Json(name = "server_now") val serverNow: String? = null,
)

data class StaffReminderDto(
    val id: Long,
    val title: String,
    @Json(name = "owner_id") val ownerId: Long,
    @Json(name = "assignee_id") val assigneeId: Long,
    @Json(name = "assignee_name") val assigneeName: String,
    @Json(name = "assignee_active") val assigneeActive: Boolean,
    @Json(name = "due_date") val dueDate: String,
    @Json(name = "advance_notice_days") val advanceNoticeDays: Int,
    val recurrence: String,
    @Json(name = "is_active") val isActive: Boolean,
    val version: Long,
    @Json(name = "can_edit") val canEdit: Boolean,
    @Json(name = "can_assign") val canAssign: Boolean,
)

data class ReminderOccurrenceDto(
    val id: Long,
    @Json(name = "reminder_id") val reminderId: Long,
    val title: String,
    @Json(name = "assignee_id") val assigneeId: Long,
    @Json(name = "assignee_name") val assigneeName: String,
    @Json(name = "due_date") val dueDate: String,
    @Json(name = "notice_date") val noticeDate: String,
    @Json(name = "completed_at") val completedAt: String? = null,
    @Json(name = "completed_by_id") val completedById: Long? = null,
    @Json(name = "is_active") val isActive: Boolean,
    @Json(name = "can_complete") val canComplete: Boolean,
    @Json(name = "definition_version") val definitionVersion: Long,
)

data class ReminderAssignmentRequestDto(val version: Long, @Json(name = "assignee_id") val assigneeId: Long)
data class ReminderCompleteRequestDto(val version: Long)
