from PyQt6.QtCore import QObject

from animation_clip import AnimationClip
from pet_state import PetState


class PetAnimator(QObject):
    def __init__(self, pet, animation_player, parent=None):
        super().__init__(parent)
        self.pet = pet
        self.animation_player = animation_player

        self.current_clip: AnimationClip | None = None
        self.logical_state: PetState | None = None

        self.queued_state_after_exit: PetState | None = None

        self.direct_clip_map: dict[PetState, AnimationClip] = {
            PetState.IDLE: AnimationClip.IDLE,
            PetState.WALK: AnimationClip.WALK,
            PetState.FALLING: AnimationClip.FALLING,
            PetState.FALLING_RECOVERY: AnimationClip.FALLING_RECOVERY,
            PetState.CLEANING: AnimationClip.CLEANING,
            PetState.ALERT: AnimationClip.ALERT,
            PetState.RUN: AnimationClip.RUN,
            PetState.DIG: AnimationClip.DIG,
            PetState.SWAT: AnimationClip.SWAT,
        }

    def request_state(self, state: PetState, force: bool = False):
        previous_logical_state = self.logical_state
        self.logical_state = state

        if state == PetState.SLEEP:
            self._request_sleep(force=force)
            return

        if previous_logical_state == PetState.SLEEP or self.current_clip in {
            AnimationClip.SLEEP_ENTER,
            AnimationClip.SLEEP_LOOP,
        }:
            self.queued_state_after_exit = state

            if self.current_clip != AnimationClip.SLEEP_EXIT or force:
                self._play_clip(AnimationClip.SLEEP_EXIT, force=True)
            return

        clip = self.direct_clip_map.get(state)
        if clip is not None:
            self._play_clip(clip, force=force)

    def on_animation_finished(self, animation_name: str):
        try:
            clip = AnimationClip(animation_name)
        except ValueError:
            return

        if clip == AnimationClip.SLEEP_ENTER:
            self._play_clip(AnimationClip.SLEEP_LOOP, force=True)
            return

        if clip == AnimationClip.SLEEP_EXIT:
            target_state = self.queued_state_after_exit or PetState.IDLE
            self.queued_state_after_exit = None

            clip = self.direct_clip_map.get(target_state)
            if clip is not None:
                self._play_clip(clip, force=True)
            return

    def _request_sleep(self, force: bool = False):
        if self.current_clip in {AnimationClip.SLEEP_ENTER, AnimationClip.SLEEP_LOOP} and not force:
            return

        self.queued_state_after_exit = None
        self._play_clip(AnimationClip.SLEEP_ENTER, force=True)

    def _play_clip(self, clip: AnimationClip, force: bool = False):
        self.current_clip = clip
        self.animation_player.set_animation(clip.value, force=force)
