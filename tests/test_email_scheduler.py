"""Tests for email service, scheduler, and scan/email API endpoints."""

from datetime import date
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from knowitall.config import EmailConfig, SchedulerConfig, get_config
from knowitall.models.digest import DailyDigest
from knowitall.models.scout_report import ScoutReport
from knowitall.services.email_service import (
    send_digest_email,
    _build_digest_html,
    _build_scout_html,
)
from knowitall.services import scheduler as scheduler_service


@pytest.fixture(autouse=True)
def _reset_scheduler_state():
    """Reset shared scheduler state between tests."""
    scheduler_service.latest_digest = None
    scheduler_service.latest_scout = None
    yield
    scheduler_service.latest_digest = None
    scheduler_service.latest_scout = None


@pytest.fixture
def client():
    """Provide a TestClient that bypasses the lifespan scheduler."""
    from knowitall.main import app

    with patch("knowitall.main.start_scheduler"), patch(
        "knowitall.main.stop_scheduler"
    ):
        with TestClient(app) as c:
            yield c


@pytest.fixture
def sample_digest():
    return DailyDigest(
        date=date(2025, 1, 1),
        headline="knowItAll — January 01, 2025",
    )


@pytest.fixture
def sample_scout():
    return ScoutReport(date=date(2025, 1, 1), headline="Scout Report — Jan 1")


# --- EmailConfig tests ---


class TestEmailConfig:
    def test_default_recipient(self):
        cfg = get_config()
        assert cfg.email.recipient == "matusvec@gmail.com"

    def test_default_smtp_host(self):
        cfg = get_config()
        assert cfg.email.smtp_host == "smtp.gmail.com"

    def test_default_smtp_port(self):
        cfg = get_config()
        assert cfg.email.smtp_port == 587


# --- SchedulerConfig tests ---


class TestSchedulerConfig:
    def test_default_scan_time(self):
        cfg = get_config()
        assert cfg.scheduler.scan_hour == 5
        assert cfg.scheduler.scan_minute == 30

    def test_default_email_time(self):
        cfg = get_config()
        assert cfg.scheduler.email_hour == 6
        assert cfg.scheduler.email_minute == 0


# --- Email service tests ---


class TestBuildDigestHtml:
    def test_contains_headline(self, sample_digest):
        html = _build_digest_html(sample_digest)
        assert "January 01, 2025" in html

    def test_contains_signal_count(self, sample_digest):
        html = _build_digest_html(sample_digest)
        assert "0 signals" in html


class TestBuildScoutHtml:
    def test_contains_headline(self, sample_scout):
        html = _build_scout_html(sample_scout)
        assert "Scout Report" in html

    def test_contains_signal_count(self, sample_scout):
        html = _build_scout_html(sample_scout)
        assert "0 signals" in html


class TestSendDigestEmail:
    def test_skips_when_no_credentials(self, sample_digest):
        cfg = EmailConfig(smtp_user="", smtp_password="")
        result = send_digest_email(sample_digest, cfg)
        assert result is False

    @patch("knowitall.services.email_service.smtplib.SMTP")
    def test_sends_when_configured(self, mock_smtp_class, sample_digest):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        cfg = EmailConfig(
            smtp_user="user@test.com",
            smtp_password="pass",
            recipient="matusvec@gmail.com",
        )
        result = send_digest_email(sample_digest, cfg)
        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@test.com", "pass")
        mock_server.sendmail.assert_called_once()

    @patch("knowitall.services.email_service.smtplib.SMTP")
    def test_returns_false_on_smtp_error(self, mock_smtp_class, sample_digest):
        mock_smtp_class.return_value.__enter__ = MagicMock(
            side_effect=Exception("SMTP failure")
        )
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        cfg = EmailConfig(
            smtp_user="user@test.com",
            smtp_password="pass",
        )
        result = send_digest_email(sample_digest, cfg)
        assert result is False


# --- Scheduler tests ---


class TestScheduler:
    def test_start_and_stop(self):
        cfg = get_config()
        sched = scheduler_service.start_scheduler(cfg)
        assert sched is not None
        assert sched.running
        jobs = sched.get_jobs()
        job_ids = {j.id for j in jobs}
        assert "daily_scan" in job_ids
        assert "daily_email" in job_ids
        scheduler_service.stop_scheduler()

    def test_run_scheduled_email_no_data(self):
        scheduler_service.latest_digest = None
        # Should not raise
        scheduler_service.run_scheduled_email()


# --- API endpoint tests ---


class TestScanNowEndpoint:
    @patch("knowitall.services.scheduler._run_scan")
    def test_scan_now_success(self, mock_run_scan, client, sample_digest, sample_scout):
        async def fake_scan(cfg):
            return sample_digest, sample_scout

        mock_run_scan.side_effect = fake_scan

        resp = client.post("/api/scan-now")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "digest_signals" in data
        assert "scout_signals" in data


class TestSendEmailEndpoint:
    def test_send_email_no_scan(self, client):
        resp = client.post("/api/send-email")
        assert resp.status_code == 400
        data = resp.json()
        assert data["status"] == "error"
        assert "No scan results" in data["detail"]

    @patch("knowitall.api.routes.send_digest_email", return_value=True)
    def test_send_email_success(self, mock_send, client, sample_digest, sample_scout):
        scheduler_service.latest_digest = sample_digest
        scheduler_service.latest_scout = sample_scout

        resp = client.post("/api/send-email")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        mock_send.assert_called_once()

    @patch("knowitall.api.routes.send_digest_email", return_value=False)
    def test_send_email_failure(self, mock_send, client, sample_digest):
        scheduler_service.latest_digest = sample_digest

        resp = client.post("/api/send-email")
        assert resp.status_code == 500
        data = resp.json()
        assert data["status"] == "error"
