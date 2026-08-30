package com.naveenhospital.medtrack.core.network.api

import android.util.Log
import com.naveenhospital.medtrack.core.network.model.AuthSessionDto
import com.naveenhospital.medtrack.core.network.model.RefreshTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.UpdateCaseRequestDtoJsonAdapterFactory
import okhttp3.Authenticator
import okhttp3.MediaType.Companion.toMediaType
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.naveenhospital.medtrack.core.network.model.UserProfileDto
import com.naveenhospital.medtrack.core.network.model.requireSessionBinding
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.Route
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.HttpException
import com.squareup.moshi.JsonDataException
import java.io.IOException

class RetryableSessionRefreshException(cause: Throwable? = null) : IOException(
    "Unable to refresh the verified MEDTRACK session.",
    cause,
)

object MedtrackNetwork {
    fun create(
        baseUrl: String,
        accessTokenProvider: () -> String? = { null },
        refreshTokenProvider: () -> String? = { null },
        expectedAccountIdProvider: () -> String? = { null },
        expectedMobileDeviceIdProvider: () -> String? = { null },
        sessionIncarnationProvider: () -> String? = { null },
        sessionUpdater: (access: String, refresh: String?) -> Boolean = { _, _ -> false },
        enableDebugLogging: Boolean = false,
    ): MedtrackApi {
        val normalizedBaseUrl = baseUrl.withTrailingSlash()
        val moshi = contractMoshi()
        val clientBuilder = OkHttpClient.Builder()
            .addInterceptor { chain ->
                val token = accessTokenProvider()
                val request = if (token.isNullOrBlank()) {
                    chain.request()
                } else {
                    chain.request().newBuilder()
                        .header("Authorization", "Bearer $token")
                        .build()
                }
                chain.proceed(request)
            }
            .authenticator(
                RefreshTokenAuthenticator(
                    baseUrl = normalizedBaseUrl,
                    accessTokenProvider = accessTokenProvider,
                    refreshTokenProvider = refreshTokenProvider,
                    expectedAccountIdProvider = expectedAccountIdProvider,
                    expectedMobileDeviceId = expectedMobileDeviceIdProvider(),
                    expectedSessionIncarnation = sessionIncarnationProvider()
                        ?.takeIf { it.isNotBlank() },
                    currentSessionIncarnationProvider = sessionIncarnationProvider,
                    sessionUpdater = sessionUpdater,
                    moshi = moshi,
                ),
            )
        if (enableDebugLogging) {
            clientBuilder.addInterceptor { chain ->
                val request = chain.request()
                Log.d(DEBUG_LOG_TAG, "--> ${safeRequestLabel(request.method, request.url.encodedPath)}")
                val response = chain.proceed(request)
                Log.d(DEBUG_LOG_TAG, "<-- ${response.code} ${safeRequestLabel(request.method, request.url.encodedPath)}")
                response
            }
        }
        val client = clientBuilder.build()
        return Retrofit.Builder()
            .baseUrl(normalizedBaseUrl)
            .client(client)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
            .create(MedtrackApi::class.java)
    }

    internal fun safeRequestLabel(method: String, encodedPath: String): String {
        val redactedPath = encodedPath.replace(NUMERIC_PATH_SEGMENT, "/{id}")
        return "$method $redactedPath"
    }

    internal fun contractMoshi(): Moshi = Moshi.Builder()
        .add(UpdateCaseRequestDtoJsonAdapterFactory)
        .add(KotlinJsonAdapterFactory())
        .build()

    private const val DEBUG_LOG_TAG = "MedtrackHttp"
    private val NUMERIC_PATH_SEGMENT = Regex("/\\d+(?=/|$)")
}

private fun String.withTrailingSlash(): String = if (endsWith("/")) this else "$this/"

private class RefreshTokenAuthenticator(
    private val baseUrl: String,
    private val accessTokenProvider: () -> String?,
    private val refreshTokenProvider: () -> String?,
    private val expectedAccountIdProvider: () -> String?,
    private val expectedMobileDeviceId: String?,
    private val expectedSessionIncarnation: String?,
    private val currentSessionIncarnationProvider: () -> String?,
    private val sessionUpdater: (access: String, refresh: String?) -> Boolean,
    private val moshi: Moshi,
) : Authenticator {
    private val refreshClient = OkHttpClient()
    private val refreshRequestAdapter = moshi.adapter(RefreshTokenRequestDto::class.java)
    private val sessionAdapter = moshi.adapter(AuthSessionDto::class.java)
    override fun authenticate(route: Route?, response: Response): Request? {
        if (response.request.url.encodedPath.endsWith("/api/auth/token/refresh/")) return null
        if (response.responseCount() >= MAX_AUTH_ATTEMPTS) return null
        val expectedAccountId = expectedAccountIdProvider()?.takeIf { it.isNotBlank() } ?: return null
        val sessionIncarnation = expectedSessionIncarnation ?: return null
        if (currentSessionIncarnationProvider() != sessionIncarnation) return null

        val requestToken = response.request.bearerToken()
        val currentToken = accessTokenProvider()?.takeIf { it.isNotBlank() }
        if (currentSessionIncarnationProvider() != sessionIncarnation) return null
        if (!currentToken.isNullOrBlank() && currentToken != requestToken) {
            return response.request.withBearer(currentToken)
        }

        val refreshToken = refreshTokenProvider()?.takeIf { it.isNotBlank() } ?: return null
        return synchronized(this) {
            if (expectedAccountIdProvider() != expectedAccountId) return@synchronized null
            if (currentSessionIncarnationProvider() != sessionIncarnation) return@synchronized null
            val updatedToken = accessTokenProvider()?.takeIf { it.isNotBlank() }
            if (!updatedToken.isNullOrBlank() && updatedToken != requestToken) {
                return@synchronized response.request.withBearer(updatedToken)
            }
            if (currentSessionIncarnationProvider() != sessionIncarnation) return@synchronized null

            val session = when (val refresh = refreshSession(refreshToken)) {
                is AutomaticRefreshAttempt.Success -> refresh.session
                is AutomaticRefreshAttempt.RetryableFailure -> throw RetryableSessionRefreshException(refresh.cause)
                AutomaticRefreshAttempt.DefinitiveFailure -> return@synchronized null
            }
            if (currentSessionIncarnationProvider() != sessionIncarnation) return@synchronized null
            if (
                runCatching {
                    session.requireSessionBinding(expectedAccountId, expectedMobileDeviceId)
                }.isFailure
            ) {
                return@synchronized null
            }
            val access = session.access.takeIf { it.isNotBlank() } ?: return@synchronized null
            val profile = when (val verification = verifyAccessToken(access)) {
                is AutomaticVerificationAttempt.Success -> verification.profile
                is AutomaticVerificationAttempt.RetryableFailure -> {
                    throw RetryableSessionRefreshException(verification.cause)
                }
                AutomaticVerificationAttempt.DefinitiveFailure -> return@synchronized null
            }
            if (currentSessionIncarnationProvider() != sessionIncarnation) return@synchronized null
            if (profile.id.toString() != expectedAccountId) return@synchronized null
            if (expectedAccountIdProvider() != expectedAccountId) return@synchronized null
            if (currentSessionIncarnationProvider() != sessionIncarnation) return@synchronized null
            if (!sessionUpdater(access, session.refresh)) return@synchronized null
            if (expectedAccountIdProvider() != expectedAccountId) return@synchronized null
            if (currentSessionIncarnationProvider() != sessionIncarnation) return@synchronized null
            response.request.withBearer(access)
        }
    }

    private fun verifyAccessToken(accessToken: String): AutomaticVerificationAttempt = try {
        val profile = kotlinx.coroutines.runBlocking {
            val client = OkHttpClient.Builder()
                .addInterceptor { chain -> chain.proceed(chain.request().withBearer(accessToken)) }
                .build()
            Retrofit.Builder()
                .baseUrl(baseUrl)
                .client(client)
                .addConverterFactory(MoshiConverterFactory.create(moshi))
                .build()
                .create(MedtrackApi::class.java)
                .me()
        }
        AutomaticVerificationAttempt.Success(profile)
    } catch (failure: Throwable) {
        when {
            failure is JsonDataException -> AutomaticVerificationAttempt.DefinitiveFailure
            failure is HttpException && failure.code() in setOf(400, 401, 403) -> {
                AutomaticVerificationAttempt.DefinitiveFailure
            }
            failure is IOException || failure is HttpException -> {
                AutomaticVerificationAttempt.RetryableFailure(failure)
            }
            else -> AutomaticVerificationAttempt.DefinitiveFailure
        }
    }

    private fun refreshSession(refreshToken: String): AutomaticRefreshAttempt {
        val body = refreshRequestAdapter
            .toJson(RefreshTokenRequestDto(refresh = refreshToken))
            .toRequestBody(JSON)
        val request = Request.Builder()
            .url("${baseUrl}api/auth/token/refresh/")
            .post(body)
            .build()
        return try {
            refreshClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    return if (response.code in setOf(400, 401, 403)) {
                        AutomaticRefreshAttempt.DefinitiveFailure
                    } else {
                        AutomaticRefreshAttempt.RetryableFailure(
                            IOException("Refresh endpoint returned HTTP ${response.code}."),
                        )
                    }
                }
                val payload = response.body?.string()?.takeIf { it.isNotBlank() }
                    ?: return AutomaticRefreshAttempt.DefinitiveFailure
                val session = try {
                    sessionAdapter.fromJson(payload)
                } catch (_: JsonDataException) {
                    return AutomaticRefreshAttempt.DefinitiveFailure
                } ?: return AutomaticRefreshAttempt.DefinitiveFailure
                AutomaticRefreshAttempt.Success(session)
            }
        } catch (failure: IOException) {
            AutomaticRefreshAttempt.RetryableFailure(failure)
        }
    }

    private companion object {
        val JSON = "application/json; charset=utf-8".toMediaType()
        const val MAX_AUTH_ATTEMPTS = 2
    }
}

private sealed interface AutomaticRefreshAttempt {
    data class Success(val session: AuthSessionDto) : AutomaticRefreshAttempt
    data class RetryableFailure(val cause: Throwable) : AutomaticRefreshAttempt
    data object DefinitiveFailure : AutomaticRefreshAttempt
}

private sealed interface AutomaticVerificationAttempt {
    data class Success(val profile: UserProfileDto) : AutomaticVerificationAttempt
    data class RetryableFailure(val cause: Throwable) : AutomaticVerificationAttempt
    data object DefinitiveFailure : AutomaticVerificationAttempt
}

private fun Response.responseCount(): Int {
    var count = 1
    var prior = priorResponse
    while (prior != null) {
        count += 1
        prior = prior.priorResponse
    }
    return count
}

private fun Request.bearerToken(): String? =
    header("Authorization")
        ?.removePrefix("Bearer")
        ?.trim()
        ?.takeIf { it.isNotBlank() }

private fun Request.withBearer(token: String): Request =
    newBuilder()
        .header("Authorization", "Bearer $token")
        .build()
