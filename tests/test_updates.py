from frm.updates import newest_release, version_tuple


def release(tag, **extra):
    return dict(tag_name=tag, html_url=f"https://github.com/lucaauletta/frm/releases/tag/{tag}",
                assets=[{"name": "FRM.exe"}], **extra)


def test_numeric_release_order_and_preview():
    assert newest_release([release("v0.9.0"), release("v0.10.0", prerelease=True)], "0.3.0")["tag_name"] == "v0.10.0"
    assert newest_release([release("v0.3.0")], "0.3.0") is None


def test_ignore_draft_malformed_foreign_and_unpublished():
    foreign = release("v9.0.0"); foreign["html_url"] = "https://example.com/download"
    empty = release("v8.0.0"); empty["assets"] = []
    assert newest_release([release("v7.0.0", draft=True), release("dev"), foreign, empty], "0.3.0") is None
    assert version_tuple("v1.2.3") == (1, 2, 3)
