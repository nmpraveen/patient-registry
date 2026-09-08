package com.naveenhospital.medtrack.core.network.api

import com.naveenhospital.medtrack.core.network.model.*
import retrofit2.http.*

/** Existing JWT/session transport; all operations remain online and server-authorized. */
interface StaffOperationsApi {
    @GET("api/staff/directory/")
    suspend fun directory(
        @Query("q") query: String = "",
        @Query("favourites") favourites: Boolean = false,
        @Query("page") page: Int = 1,
    ): StaffPageDto<DirectoryContactDto>

    @GET("api/staff/directory/{id}/")
    suspend fun directoryContact(@Path("id") id: Long): DirectoryContactDto

    @PUT("api/staff/directory/{id}/favourite/")
    suspend fun setDirectoryFavourite(@Path("id") id: Long, @Body request: FavouriteRequestDto): DirectoryContactDto

    @GET("api/staff/announcements/")
    suspend fun staffAnnouncements(@Query("page") page: Int = 1): StaffPageDto<StaffAnnouncementDto>

    @GET("api/staff/announcements/{id}/")
    suspend fun staffAnnouncement(@Path("id") id: Long): StaffAnnouncementDto

    @GET("api/staff/reminders/occurrences/")
    suspend fun reminderOccurrences(
        @Query("status") status: String = "pending",
        @Query("reminder_id") reminderId: Long? = null,
        @Query("page") page: Int = 1,
    ): StaffPageDto<ReminderOccurrenceDto>

    @GET("api/staff/reminders/{id}/")
    suspend fun staffReminder(@Path("id") id: Long): StaffReminderDto

    @GET("api/staff/reminders/assignees/")
    suspend fun reminderAssignees(@Query("q") query: String = "", @Query("page") page: Int = 1): StaffPageDto<StaffPersonDto>

    @PATCH("api/staff/reminders/{id}/")
    suspend fun assignReminder(@Path("id") id: Long, @Body request: ReminderAssignmentRequestDto): StaffReminderDto

    @POST("api/staff/reminders/occurrences/{id}/complete/")
    suspend fun completeReminder(@Path("id") id: Long, @Body request: ReminderCompleteRequestDto): ReminderOccurrenceDto
}
