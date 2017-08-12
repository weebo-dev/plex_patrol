#!/usr/bin/env python2.7
import thread
import time

from utils import config
from utils import logger
from utils.plex import Plex

log = logger.get_root_logger()
server = None
watchlist = []
ip_watchlist = {}


def kill_paused_stream(stream, check_again_mins, kick_reason):
    log.info("%s will have their stream killed in %d mins, unless it is resumed", stream.user, check_again_mins)
    time.sleep(60 * check_again_mins)
    current_streams = server.get_streams()
    if current_streams is None:
        log.error(
            "Unable to check if %s stream is still paused because there was an error retrieving the active streams...",
            stream.user)
        watchlist.remove(stream.session_id)
        return

    for current_stream in current_streams:
        if current_stream.session_id == stream.session_id:
            if current_stream.state == 'paused':
                if server.kill_stream(stream.session_id, kick_reason):
                    log.info("Kicked %s because their stream was still paused %d minutes later", stream.user,
                             check_again_mins)
                    watchlist.remove(stream.session_id)
                    return
                else:
                    log.error("Unable to kick the stream of %s, not sure why...", stream.user)
                    watchlist.remove(stream.session_id)
                    return
            else:
                log.info("%s stream was resumed, so we wont kill their stream, their in the clear!", stream.user)
                watchlist.remove(stream.session_id)
                return
    log.info("%s is no longer streaming...", stream.user)
    watchlist.remove(stream.session_id)


def should_kick_stream(stream):
    # is stream using a blacklisted client
    for client in config.KICK_CLIENT_PLAYERS:
        if client.lower() in stream.player.lower():
            return True, 0, config.KICK_PLAYER_MESSAGE

    # is this user already streaming from another ip
    if config.KICK_MULTIPLE_IP:
        if stream.user in ip_watchlist:
            if stream.ip != ip_watchlist[stream.user]:
                return True, 0, config.KICK_MULTI_IP_MESSAGE
        else:
            ip_watchlist[stream.user] = stream.ip

    if stream.type == 'transcode':
        # stream is transcode - check specifics
        if stream.audio_decision == 'transcode' and config.KICK_AUDIO_TRANSCODES:
            return True, 0, config.KICK_TRANSCODE_MESSAGE
        elif stream.video_decision == 'transcode' and config.KICK_VIDEO_TRANSCODES:
            return True, 0, config.KICK_TRANSCODE_MESSAGE
        if stream.state == 'paused' and config.KICK_PAUSED_TRANSCODES:
            return True, config.KICK_PAUSED_GRACE_MINS, config.KICK_PAUSED_MESSAGE

    else:
        # stream is directplay - check specifics
        if stream.state == 'paused' and config.KICK_PAUSED_DIRECTPLAY:
            return True, config.KICK_PAUSED_GRACE_MINS, config.KICK_PAUSED_MESSAGE
    return False, 0, None


def check_streams():
    log.debug("Retrieving active stream(s) for server: %s", server.name)
    streams = server.get_streams()
    if streams is None:
        log.error("There was an error while retrieving the active streams...")
        return
    elif not streams:
        log.info("There's currently no streams to check")
        return
    else:
        log.debug("Checking %d stream(s)", len(streams))

    # clear ip watchlist before checking streams
    ip_watchlist.clear()
    # iterate streams and check / kick
    for stream in streams:
        if stream.user in config.WHITELISTED_USERS:
            log.info("Skipping whitelisted user: %s", stream.user)
            continue
        else:
            log.info("Checking stream: %s", stream)
        kick_stream, kick_mins, kick_msg = should_kick_stream(stream)
        if kick_stream:
            if not kick_mins:
                # kick instantly....
                if server.kill_stream(stream.session_id, kick_msg):
                    log.info("Kicked %s instantly, without a second thought", stream.user)
                else:
                    log.error("Unable to kick the stream of %s, not sure why...", stream.user)
            else:
                # kick in X mins unless resumed
                # is session already being watched?
                if stream.session_id in watchlist:
                    log.info("%s stream is already on the watchlist, skipping..", stream.user)
                else:
                    thread.start_new_thread(kill_paused_stream, (stream, kick_mins, kick_msg))
                    watchlist.append(stream.session_id)
    log.debug("Finished checking streams")


if __name__ == "__main__":
    log.info("Initializing")
    log.info("Validating server %r with token %r", config.SERVER_URL, config.SERVER_TOKEN)
    server = Plex(config.SERVER_NAME, config.SERVER_URL, config.SERVER_TOKEN)
    if not server.validate():
        log.error("Could not validate server token, are you sure its correct...")
        exit(1)
    else:
        log.info("Server token was validated, proceeding to uphold the law!")

    while True:
        log.debug("Checking streams in %d seconds", config.CHECK_INTERVAL)
        time.sleep(config.CHECK_INTERVAL)
        check_streams()
