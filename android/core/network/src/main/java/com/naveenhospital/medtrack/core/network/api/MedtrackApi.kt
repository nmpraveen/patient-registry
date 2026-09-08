package com.naveenhospital.medtrack.core.network.api

import com.naveenhospital.medtrack.core.network.model.ApiMessageDto
import com.naveenhospital.medtrack.core.network.model.CategoriesResponseDto
import com.naveenhospital.medtrack.core.network.model.AuthSessionDto
import com.naveenhospital.medtrack.core.network.model.CaseCreateResponseDto
import com.naveenhospital.medtrack.core.network.model.CaseDetailDto
import com.naveenhospital.medtrack.core.network.model.CaseEditFormDto
import com.naveenhospital.medtrack.core.network.model.CaseFormMetadataDto
import com.naveenhospital.medtrack.core.network.model.CaseListResponseDto
import com.naveenhospital.medtrack.core.network.model.CaseSearchRequestDto
import com.naveenhospital.medtrack.core.network.model.CaseSearchResponseDto
import com.naveenhospital.medtrack.core.network.model.CaseUpdateResponseDto
import com.naveenhospital.medtrack.core.network.model.ClientWriteRequestDto
import com.naveenhospital.medtrack.core.network.model.CreateCaseRequestDto
import com.naveenhospital.medtrack.core.network.model.CreateTaskRequestDto
import com.naveenhospital.medtrack.core.network.model.LogCallRequestDto
import com.naveenhospital.medtrack.core.network.model.TaskFormMetadataDto
import com.naveenhospital.medtrack.core.network.model.TaskNoteRequestDto
import com.naveenhospital.medtrack.core.network.model.UpdateTaskRequestDto
import com.naveenhospital.medtrack.core.network.model.UpdateCaseRequestDto
import com.naveenhospital.medtrack.core.network.model.VitalsUpdateRequestDto
import com.naveenhospital.medtrack.core.network.model.PatientSearchResponseDto
import com.naveenhospital.medtrack.core.network.model.PatientSearchRequestDto
import com.naveenhospital.medtrack.core.network.model.LoginRequestDto
import com.naveenhospital.medtrack.core.network.model.LoginResponseDto
import com.naveenhospital.medtrack.core.network.model.NotificationsResponseDto
import com.naveenhospital.medtrack.core.network.model.RefreshTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.RegisterPushTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.CallWriteResponseDto
import com.naveenhospital.medtrack.core.network.model.TaskWriteResponseDto
import com.naveenhospital.medtrack.core.network.model.UserProfileDto
import com.naveenhospital.medtrack.core.network.model.VitalsRequestDto
import com.naveenhospital.medtrack.core.network.model.VitalsThresholdsDto
import com.naveenhospital.medtrack.core.network.model.VitalsWriteResponseDto
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.Response

interface MedtrackApi : StaffOperationsApi {
    @GET("api/cases/{caseId}/related/")
    suspend fun relatedCases(
        @Path("caseId") caseId: String,
        @Query("cursor") cursor: String? = null,
    ): com.naveenhospital.medtrack.core.network.model.RelatedCasePageDto

    @GET("api/upcoming/")
    suspend fun upcoming(
        @Query("start_date") startDate: String? = null,
        @Query("cursor") cursor: String? = null,
        @Query("category") categories: List<String>? = null,
        @Query("subcategory") subcategories: List<String>? = null,
        @Query("assigned_to") assignedTo: String? = null,
        @Query("scope_context") scopeContext: String? = null,
    ): com.naveenhospital.medtrack.core.network.model.UpcomingPageDto

    @POST("api/upcoming/search/")
    suspend fun searchUpcoming(@Body request: com.naveenhospital.medtrack.core.network.model.UpcomingSearchRequestDto): com.naveenhospital.medtrack.core.network.model.UpcomingPageDto

    @GET("api/cases/{caseId}/timeline/")
    suspend fun caseTimeline(
        @Path("caseId") caseId: String,
        @Query("filter") filter: String = "all",
        @Query("cursor") cursor: String? = null,
    ): com.naveenhospital.medtrack.core.network.model.CaseTimelinePageDto

    @POST("api/auth/token/")
    suspend fun login(@Body request: LoginRequestDto): Response<LoginResponseDto>

    @POST("api/auth/token/refresh/")
    suspend fun refresh(@Body request: RefreshTokenRequestDto): AuthSessionDto

    @POST("api/auth/logout/")
    suspend fun logout(@Body request: RefreshTokenRequestDto): ApiMessageDto

    @GET("api/me/")
    suspend fun me(): UserProfileDto

    @GET("api/cases/")
    suspend fun listCases(
        @Query("bucket") bucket: String? = null,
        @Query("assigned_to") assignedTo: String? = null,
        @Query("scope_context") scopeContext: String? = null,
        @Query("category") categories: List<String>? = null,
        @Query("subcategory") subcategories: List<String>? = null,
        @Query("page") page: Int? = null,
    ): CaseListResponseDto

    @POST("api/cases/search/")
    suspend fun searchCases(@Body request: CaseSearchRequestDto): CaseSearchResponseDto

    @POST("api/cases/")
    suspend fun createCase(@Body request: CreateCaseRequestDto): CaseCreateResponseDto

    @POST("api/patients/")
    suspend fun searchPatients(@Body request: PatientSearchRequestDto): PatientSearchResponseDto

    @GET("api/metadata/case-form/")
    suspend fun caseFormMetadata(): CaseFormMetadataDto

    @GET("api/metadata/task-form/")
    suspend fun taskFormMetadata(): TaskFormMetadataDto

    @GET("api/cases/{caseId}/")
    suspend fun caseDetail(@Path("caseId") caseId: String): CaseDetailDto

    @GET("api/cases/{caseId}/edit-form/")
    suspend fun caseEditForm(@Path("caseId") caseId: String): CaseEditFormDto

    @POST("api/cases/{caseId}/anc/")
    suspend fun ancAction(@Path("caseId") caseId: String, @Body request: Map<String, @JvmSuppressWildcards Any>): CaseUpdateResponseDto

    @PATCH("api/cases/{caseId}/")
    suspend fun updateCase(
        @Path("caseId") caseId: String,
        @Body request: UpdateCaseRequestDto,
    ): CaseUpdateResponseDto

    @POST("api/cases/{caseId}/tasks/")
    suspend fun createTask(
        @Path("caseId") caseId: String,
        @Body request: CreateTaskRequestDto,
    ): TaskWriteResponseDto

    @PATCH("api/tasks/{taskId}/")
    suspend fun updateTask(
        @Path("taskId") taskId: String,
        @Body request: UpdateTaskRequestDto,
    ): TaskWriteResponseDto

    @POST("api/tasks/{taskId}/note/")
    suspend fun addTaskNote(
        @Path("taskId") taskId: String,
        @Body request: TaskNoteRequestDto,
    ): TaskWriteResponseDto

    @PATCH("api/vitals/{vitalId}/")
    suspend fun updateVitals(
        @Path("vitalId") vitalId: String,
        @Body request: VitalsUpdateRequestDto,
    ): VitalsWriteResponseDto

    @POST("api/tasks/{taskId}/complete/")
    suspend fun completeTask(
        @Path("taskId") taskId: String,
        @Body request: ClientWriteRequestDto,
    ): TaskWriteResponseDto

    @POST("api/cases/{caseId}/call-outcome/")
    suspend fun logCall(
        @Path("caseId") caseId: String,
        @Body request: LogCallRequestDto,
    ): CallWriteResponseDto

    @POST("api/cases/{caseId}/vitals/")
    suspend fun addVitals(
        @Path("caseId") caseId: String,
        @Body request: VitalsRequestDto,
    ): VitalsWriteResponseDto

    @GET("api/vitals-thresholds/")
    suspend fun vitalsThresholds(): VitalsThresholdsDto

    @GET("api/notifications/")
    suspend fun notifications(
        @Query("type") type: String? = null,
        @Query("unread_only") unreadOnly: Boolean? = null,
        @Query("cursor") cursor: String? = null,
        @Query("page_size") pageSize: Int? = null,
    ): NotificationsResponseDto

    @POST("api/notifications/{notificationId}/read/")
    suspend fun markNotificationRead(@Path("notificationId") notificationId: String): ApiMessageDto

    @POST("api/devices/")
    suspend fun registerPushToken(@Body request: RegisterPushTokenRequestDto): ApiMessageDto

    @GET("api/metadata/categories/")
    suspend fun categories(): CategoriesResponseDto
}
