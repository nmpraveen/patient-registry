package com.naveenhospital.medtrack.core.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.paging.PagingSource
import kotlinx.coroutines.flow.Flow

@Dao
interface CaseDao {
    @Query("SELECT * FROM cases ORDER BY nextTaskDueDate IS NULL, nextTaskDueDate ASC, patientName ASC")
    fun observeCases(): Flow<List<CaseEntity>>

    @Query("SELECT * FROM cases ORDER BY nextTaskDueDate IS NULL, nextTaskDueDate ASC, patientName ASC")
    fun pagingSource(): PagingSource<Int, CaseEntity>

    @Query("SELECT * FROM cases WHERE id = :caseId LIMIT 1")
    fun observeCase(caseId: String): Flow<CaseEntity?>

    @Query("SELECT * FROM cases WHERE id = :caseId LIMIT 1")
    suspend fun caseById(caseId: String): CaseEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertCase(caseEntity: CaseEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertCases(cases: List<CaseEntity>)

    @Query("DELETE FROM cases")
    suspend fun clearCases()
}

@Dao
interface CaseStatsDao {
    @Query("SELECT * FROM case_stats WHERE cacheKey = :cacheKey LIMIT 1")
    suspend fun statsForKey(cacheKey: String): CaseStatsEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertStats(stats: CaseStatsEntity)
}

@Dao
interface TaskDao {
    @Query("SELECT * FROM tasks WHERE caseId = :caseId ORDER BY dueDate IS NULL, dueDate ASC, id ASC")
    fun observeTasksForCase(caseId: String): Flow<List<TaskEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertTask(task: TaskEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertTasks(tasks: List<TaskEntity>)

    @Query(
        """
        UPDATE tasks
        SET status = 'COMPLETED',
            statusLabel = 'Completed',
            canComplete = 0,
            updatedAtMillis = :updatedAtMillis
        WHERE id = :taskId
        """,
    )
    suspend fun markTaskCompletedLocally(taskId: String, updatedAtMillis: Long)

    @Query("DELETE FROM tasks WHERE caseId = :caseId")
    suspend fun clearTasksForCase(caseId: String)
}

@Dao
interface VitalDao {
    @Query("SELECT * FROM vitals WHERE caseId = :caseId ORDER BY recordedAt DESC, id DESC")
    fun observeVitalsForCase(caseId: String): Flow<List<VitalEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertVital(vital: VitalEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertVitals(vitals: List<VitalEntity>)

    @Query("DELETE FROM vitals WHERE id = :vitalId")
    suspend fun deleteVital(vitalId: String)

    @Query("DELETE FROM vitals WHERE caseId = :caseId")
    suspend fun clearVitalsForCase(caseId: String)
}

@Dao
interface VitalsThresholdDao {
    @Query("SELECT * FROM vitals_thresholds WHERE id = 'current' LIMIT 1")
    suspend fun currentThresholds(): VitalsThresholdEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertThresholds(thresholds: VitalsThresholdEntity)
}

@Dao
interface CategoryOptionsDao {
    @Query("SELECT * FROM category_options WHERE id = 'current' LIMIT 1")
    suspend fun currentOptions(): CategoryOptionsEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertOptions(options: CategoryOptionsEntity)
}

@Dao
interface NotificationDao {
    @Query("SELECT * FROM notifications ORDER BY createdAt DESC")
    fun observeNotifications(): Flow<List<NotificationEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertNotifications(notifications: List<NotificationEntity>)

    @Query("UPDATE notifications SET isRead = 1 WHERE id = :notificationId")
    suspend fun markRead(notificationId: String)
}

@Dao
interface PushTokenDao {
    @Query("SELECT * FROM push_tokens WHERE syncedAtMillis <= 0 ORDER BY token ASC")
    suspend fun pendingTokens(): List<PushTokenEntity>

    @Query("SELECT * FROM push_tokens WHERE syncedAtMillis > 0 ORDER BY syncedAtMillis DESC LIMIT 1")
    suspend fun latestSyncedToken(): PushTokenEntity?

    @Query("SELECT * FROM push_tokens ORDER BY syncedAtMillis DESC, token ASC LIMIT 1")
    suspend fun latestToken(): PushTokenEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertToken(token: PushTokenEntity)

    @Query("UPDATE push_tokens SET syncedAtMillis = :syncedAtMillis WHERE token = :token")
    suspend fun markTokenSynced(token: String, syncedAtMillis: Long)

    @Query("DELETE FROM push_tokens WHERE token = :token")
    suspend fun deleteToken(token: String)
}

@Dao
interface PendingWriteDao {
    @Query("SELECT * FROM pending_writes ORDER BY createdAtMillis ASC")
    suspend fun pendingWrites(): List<PendingWriteEntity>

    @Query("SELECT COUNT(*) FROM pending_writes")
    fun observePendingWriteCount(): Flow<Int>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertPendingWrite(write: PendingWriteEntity)

    @Query(
        """
        UPDATE pending_writes
        SET retryCount = retryCount + 1,
            lastError = :lastError,
            updatedAtMillis = :updatedAtMillis
        WHERE clientWriteId = :clientWriteId
        """,
    )
    suspend fun markAttempt(clientWriteId: String, lastError: String?, updatedAtMillis: Long)

    @Query("DELETE FROM pending_writes WHERE clientWriteId = :clientWriteId")
    suspend fun deletePendingWrite(clientWriteId: String)
}

@Dao
interface SyncConflictDao {
    @Query("SELECT * FROM sync_conflicts ORDER BY createdAtMillis DESC")
    fun observeConflicts(): Flow<List<SyncConflictEntity>>

    @Query("SELECT COUNT(*) FROM sync_conflicts")
    fun observeConflictCount(): Flow<Int>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertConflict(conflict: SyncConflictEntity)

    @Query("DELETE FROM sync_conflicts WHERE clientWriteId = :clientWriteId")
    suspend fun deleteConflict(clientWriteId: String)
}

@Dao
interface CacheMetadataDao {
    @Query("SELECT updatedAtMillis FROM cache_metadata WHERE cacheKey = :cacheKey LIMIT 1")
    suspend fun updatedAtMillis(cacheKey: String): Long?

    @Query("SELECT cacheKey FROM cache_metadata WHERE cacheKey LIKE :prefix || '%'")
    suspend fun cacheKeysStartingWith(prefix: String): List<String>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertMetadata(metadata: CacheMetadataEntity)
}
