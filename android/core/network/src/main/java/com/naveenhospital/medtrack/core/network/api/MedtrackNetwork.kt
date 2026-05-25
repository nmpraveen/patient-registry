package com.naveenhospital.medtrack.core.network.api

import com.naveenhospital.medtrack.core.network.model.AuthSessionDto
import com.naveenhospital.medtrack.core.network.model.RefreshTokenRequestDto
import okhttp3.Authenticator
import okhttp3.MediaType.Companion.toMediaType
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.Route
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

object MedtrackNetwork {
    fun create(
        baseUrl: String,
        accessTokenProvider: () -> String? = { null },
        refreshTokenProvider: () -> String? = { null },
        sessionUpdater: (access: String, refresh: String?) -> Unit = { _, _ -> },
    ): MedtrackApi {
        val normalizedBaseUrl = baseUrl.withTrailingSlash()
        val moshi = Moshi.Builder()
            .add(KotlinJsonAdapterFactory())
            .build()
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }
        val client = OkHttpClient.Builder()
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
                    sessionUpdater = sessionUpdater,
                    moshi = moshi,
                ),
            )
            .addInterceptor(logging)
            .build()
        return Retrofit.Builder()
            .baseUrl(normalizedBaseUrl)
            .client(client)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
            .create(MedtrackApi::class.java)
    }
}

private fun String.withTrailingSlash(): String = if (endsWith("/")) this else "$this/"

private class RefreshTokenAuthenticator(
    private val baseUrl: String,
    private val accessTokenProvider: () -> String?,
    private val refreshTokenProvider: () -> String?,
    private val sessionUpdater: (access: String, refresh: String?) -> Unit,
    moshi: Moshi,
) : Authenticator {
    private val refreshClient = OkHttpClient()
    private val refreshRequestAdapter = moshi.adapter(RefreshTokenRequestDto::class.java)
    private val sessionAdapter = moshi.adapter(AuthSessionDto::class.java)

    override fun authenticate(route: Route?, response: Response): Request? {
        if (response.request.url.encodedPath.endsWith("/api/auth/token/refresh/")) return null
        if (response.responseCount() >= MAX_AUTH_ATTEMPTS) return null

        val requestToken = response.request.bearerToken()
        val currentToken = accessTokenProvider()?.takeIf { it.isNotBlank() }
        if (!currentToken.isNullOrBlank() && currentToken != requestToken) {
            return response.request.withBearer(currentToken)
        }

        val refreshToken = refreshTokenProvider()?.takeIf { it.isNotBlank() } ?: return null
        return synchronized(this) {
            val updatedToken = accessTokenProvider()?.takeIf { it.isNotBlank() }
            if (!updatedToken.isNullOrBlank() && updatedToken != requestToken) {
                return@synchronized response.request.withBearer(updatedToken)
            }

            val session = refreshSession(refreshToken) ?: return@synchronized null
            val access = session.access.takeIf { it.isNotBlank() } ?: return@synchronized null
            sessionUpdater(access, session.refresh)
            response.request.withBearer(access)
        }
    }

    private fun refreshSession(refreshToken: String): AuthSessionDto? {
        val body = refreshRequestAdapter
            .toJson(RefreshTokenRequestDto(refresh = refreshToken))
            .toRequestBody(JSON)
        val request = Request.Builder()
            .url("${baseUrl}api/auth/token/refresh/")
            .post(body)
            .build()
        return runCatching {
            refreshClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) return null
                val payload = response.body?.string()?.takeIf { it.isNotBlank() } ?: return null
                sessionAdapter.fromJson(payload)
            }
        }.getOrNull()
    }

    private companion object {
        val JSON = "application/json; charset=utf-8".toMediaType()
        const val MAX_AUTH_ATTEMPTS = 2
    }
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
