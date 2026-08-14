from datetime import datetime

from atv_player.models import HistoryRecord


class HistoryController:
    """播放历史列表控制器。

    后端已下线 ``/api/history``(GET/POST/DELETE 全部 404)。播放记录改由多端同步服务
    维护:PUSH 本地记录到 ``/api/playback/events``,PULL ``/api/playback/changes`` 回灌
    本地 ``media_playback_history``。因此历史列表只从本地仓库读取——它就是同步后的
    本地视图,不再发任何网络请求,避免后端缺端点时整页加载失败。
    """

    def __init__(self, api_client=None, playback_history_repository=None) -> None:
        # api_client 保留以兼容旧调用方签名,但历史读取/删除不再依赖它。
        self._api_client = api_client
        self._playback_history_repository = playback_history_repository

    def load_page(
        self,
        page: int,
        size: int,
        *,
        keyword: str = "",
        source_kind: str = "",
        time_range: str = "",
        continue_watching: bool = False,
    ) -> tuple[list[HistoryRecord], int]:
        records: list[HistoryRecord] = []
        if self._playback_history_repository is not None:
            records.extend(self._playback_history_repository.list_histories())
        records.sort(key=lambda item: item.create_time, reverse=True)
        if keyword:
            kw = keyword.lower()
            records = [r for r in records if kw in r.vod_name.lower()]
        if source_kind:
            records = [r for r in records if r.source_kind == source_kind]
        if time_range:
            now_ms = int(datetime.now().timestamp() * 1000)
            days = {"7d": 7, "30d": 30}.get(time_range, 0)
            if days:
                cutoff = now_ms - days * 86400 * 1000
                records = [r for r in records if r.create_time >= cutoff]
        if continue_watching:
            records = [r for r in records if r.position > 0]
        total = len(records)
        start = max(page - 1, 0) * size
        end = start + size
        return records[start:end], total

    def delete_one(self, record: HistoryRecord) -> None:
        if self._playback_history_repository is None:
            return
        self._playback_history_repository.delete_history(
            record.source_kind,
            record.key,
            record.source_key,
        )
        self._record_pending_deletion(record)

    def delete_many(self, records: list[HistoryRecord]) -> None:
        if self._playback_history_repository is None:
            return
        for record in records:
            self._playback_history_repository.delete_history(
                record.source_kind,
                record.key,
                record.source_key,
            )
            self._record_pending_deletion(record)

    def _record_pending_deletion(self, record: HistoryRecord) -> None:
        # 记下显式删除,供 PlaybackHistorySyncService 下次 PUSH 转成 tombstone 多端同步。
        recorder = getattr(self._playback_history_repository, "record_pending_deletion", None)
        if callable(recorder):
            recorder(record.source_kind, record.source_key, record.key, record.create_time)

    def clear_page(self, records: list[HistoryRecord]) -> None:
        self.delete_many(records)
