"""Hand-written fake S3 client: ListObjectsV2 only, paged."""

from __future__ import annotations


class FakeS3:
    def __init__(self, objects: dict[str, list[dict]], page_size: int = 2):
        self.objects = objects
        self.page_size = page_size
        self.calls: list[dict] = []

    def list_objects_v2(self, Bucket, ContinuationToken=None):
        self.calls.append({"Bucket": Bucket, "ContinuationToken": ContinuationToken})
        rows = self.objects[Bucket]
        start = int(ContinuationToken or 0)
        page = {"Contents": rows[start : start + self.page_size], "IsTruncated": False}
        if start + self.page_size < len(rows):
            page["IsTruncated"] = True
            page["NextContinuationToken"] = str(start + self.page_size)
        return page
