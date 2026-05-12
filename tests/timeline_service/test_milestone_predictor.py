"""
Milestone Predictor – Unit tests
Tests: predict_milestones() logic for GDD threshold completion and micro-trigger alerts
Pure Python, zero external I/O.
"""
import pytest
from datetime import datetime, timezone
from app.engines.milestone_predictor import predict_milestones
from app.models.timeline import (
    UserCropTimeline, UserMetadata, LifecycleState,
    Milestone, MilestoneType, MilestoneStatus,
    EnvironmentalSnapshot, GeoLocation,
)
from tests.fixtures.test_data import FARMER_UID, CROP_ID, SOWING_DATE


def _build_timeline(total_gdd: float, soil_moisture: float = 45.0) -> UserCropTimeline:
    """Factory: build a minimal timeline with realistic milestones."""
    return UserCropTimeline(
        user_metadata=UserMetadata(
            user_id=FARMER_UID,
            crop_id=CROP_ID,
            sowing_date=SOWING_DATE,
            location=GeoLocation(coordinates=[77.209, 28.614]),
            t_base=10.0,
        ),
        lifecycle_state=LifecycleState(
            current_stage="Sowing",
            progress_percentage=0.0,
            total_gdd=total_gdd,
        ),
        milestone_map=[
            Milestone(
                name="Germination",
                type=MilestoneType.MACRO,
                status=MilestoneStatus.PREDICTED,
                target_gdd=100.0,
                confidence_score=1.0,
            ),
            Milestone(
                name="Tillering",
                type=MilestoneType.MACRO,
                status=MilestoneStatus.PREDICTED,
                target_gdd=350.0,
                confidence_score=1.0,
            ),
            Milestone(
                name="Soil Moisture Alert",
                type=MilestoneType.MICRO,
                status=MilestoneStatus.PREDICTED,
                trigger_logic="soil_moisture < 20",
                confidence_score=1.0,
            ),
            Milestone(
                name="Harvest",
                type=MilestoneType.MACRO,
                status=MilestoneStatus.PREDICTED,
                target_gdd=1500.0,
                confidence_score=1.0,
            ),
        ],
        environmental_snapshot=EnvironmentalSnapshot(
            last_updated=datetime.now(timezone.utc),
            t_max=30.0,
            t_min=15.0,
            soil_moisture=soil_moisture,
            source="iot",
            weight=1.0,
        ),
    )


class TestPredictMilestones:

    def test_germination_reached(self):
        """GDD ≥ 100 → Germination transitions PREDICTED→COMPLETED."""
        tl = _build_timeline(total_gdd=110.0)
        tl = predict_milestones(tl)

        germination = next(m for m in tl.milestone_map if m.name == "Germination")
        assert germination.status == MilestoneStatus.COMPLETED
        assert germination.completed_date is not None

    def test_milestone_not_triggered_below_threshold(self):
        """GDD = 90 < 100 → Germination still PREDICTED."""
        tl = _build_timeline(total_gdd=90.0)
        tl = predict_milestones(tl)

        germination = next(m for m in tl.milestone_map if m.name == "Germination")
        assert germination.status == MilestoneStatus.PREDICTED

    def test_multiple_milestones_triggered_at_once(self):
        """GDD 400 → both Germination (100) and Tillering (350) completed."""
        tl = _build_timeline(total_gdd=400.0)
        tl = predict_milestones(tl)

        germination = next(m for m in tl.milestone_map if m.name == "Germination")
        tillering   = next(m for m in tl.milestone_map if m.name == "Tillering")
        harvest     = next(m for m in tl.milestone_map if m.name == "Harvest")

        assert germination.status == MilestoneStatus.COMPLETED
        assert tillering.status   == MilestoneStatus.COMPLETED
        assert harvest.status     == MilestoneStatus.PREDICTED   # 400 < 1500

    def test_progress_percentage_updated(self):
        """progress_percentage should reflect GDD / final_target_gdd."""
        tl = _build_timeline(total_gdd=750.0)
        tl = predict_milestones(tl)

        # 750 / 1500 = 50%
        assert tl.lifecycle_state.progress_percentage == pytest.approx(50.0)

    def test_progress_capped_at_100(self):
        """GDD > final target → progress capped at 100%."""
        tl = _build_timeline(total_gdd=2000.0)
        tl = predict_milestones(tl)

        assert tl.lifecycle_state.progress_percentage == 100.0

    def test_soil_moisture_micro_trigger_fires(self):
        """soil_moisture < 20 → Soil Moisture Alert transitions to ALERT."""
        tl = _build_timeline(total_gdd=0.0, soil_moisture=15.0)
        tl = predict_milestones(tl)

        alert = next(m for m in tl.milestone_map if m.name == "Soil Moisture Alert")
        assert alert.status == MilestoneStatus.ALERT

    def test_soil_moisture_above_threshold_no_trigger(self):
        """soil_moisture = 45 (> 20) → no ALERT."""
        tl = _build_timeline(total_gdd=0.0, soil_moisture=45.0)
        tl = predict_milestones(tl)

        alert = next(m for m in tl.milestone_map if m.name == "Soil Moisture Alert")
        assert alert.status == MilestoneStatus.PREDICTED

    def test_confidence_score_set_from_snapshot_weight(self):
        """After completion, confidence_score == snapshot.weight."""
        tl = _build_timeline(total_gdd=200.0)
        tl.environmental_snapshot.weight = 0.8
        tl = predict_milestones(tl)

        germination = next(m for m in tl.milestone_map if m.name == "Germination")
        assert germination.confidence_score == 0.8

    def test_current_stage_updated_to_completed_milestone(self):
        """lifecycle_state.current_stage reflects the last completed milestone name."""
        tl = _build_timeline(total_gdd=110.0)
        tl = predict_milestones(tl)

        assert tl.lifecycle_state.current_stage == "Germination"

    def test_already_completed_milestone_untouched(self):
        """A milestone already COMPLETED is not re-processed."""
        tl = _build_timeline(total_gdd=500.0)
        # Pre-mark Germination as complete
        tl.milestone_map[0].status = MilestoneStatus.COMPLETED
        tl.milestone_map[0].completed_date = datetime(2024, 11, 11, tzinfo=timezone.utc)

        tl = predict_milestones(tl)

        germination = next(m for m in tl.milestone_map if m.name == "Germination")
        # completed_date should NOT be overwritten
        assert germination.completed_date == datetime(2024, 11, 11, tzinfo=timezone.utc)
