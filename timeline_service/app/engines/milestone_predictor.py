import logging
from datetime import datetime, timezone
from app.models.timeline import UserCropTimeline, MilestoneStatus

logger = logging.getLogger(__name__)

def predict_milestones(timeline: UserCropTimeline) -> UserCropTimeline:
    """
    Evaluates the accumulated GDD against milestone target_gdd values.
    Transitions milestones from PREDICTED to COMPLETED.
    """
    current_gdd = timeline.lifecycle_state.total_gdd
    
    milestones_updated = False
    
    for milestone in timeline.milestone_map:
        if milestone.status == MilestoneStatus.PREDICTED:
            # 1. Check GDD for Macro Milestones
            if milestone.target_gdd is not None and current_gdd >= milestone.target_gdd:
                milestone.status = MilestoneStatus.COMPLETED
                milestone.completed_date = datetime.now(timezone.utc)
                milestone.confidence_score = timeline.environmental_snapshot.weight
                timeline.lifecycle_state.current_stage = milestone.name
                milestones_updated = True
                logger.info(f"Milestone {milestone.name} reached for user {timeline.user_metadata.user_id}")
            
            # 2. Check trigger_logic for Micro Milestones (e.g., "soil_moisture < 20")
            elif milestone.trigger_logic and timeline.environmental_snapshot:
                logic = milestone.trigger_logic.lower().replace(" ", "")
                # Safe parsing of specific metrics
                if "soil_moisture<" in logic and timeline.environmental_snapshot.soil_moisture is not None:
                    try:
                        threshold = float(logic.split("<")[1])
                        if timeline.environmental_snapshot.soil_moisture < threshold:
                            milestone.status = MilestoneStatus.ALERT
                            milestone.confidence_score = timeline.environmental_snapshot.weight
                            milestones_updated = True
                            logger.warning(f"Micro Trigger Alert: {milestone.name} for user {timeline.user_metadata.user_id}")
                    except ValueError:
                        pass
                
    if milestones_updated:
        # Recalculate overall progress percentage
        # Simplified: Progress = current_gdd / final_target_gdd
        final_milestone = timeline.milestone_map[-1]
        if final_milestone.target_gdd and final_milestone.target_gdd > 0:
            progress = (current_gdd / final_milestone.target_gdd) * 100.0
            timeline.lifecycle_state.progress_percentage = min(100.0, progress)
            
    return timeline
