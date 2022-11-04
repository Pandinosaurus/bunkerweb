#!/bin/bash

. /opt/bunkerweb/helpers/utils.sh

if [ -f /opt/bunkerweb/tmp/scheduler.pid ] ; then
	rm -f /opt/bunkerweb/tmp/scheduler.pid
fi

# trap SIGTERM and SIGINT
function trap_exit() {
	log "ENTRYPOINT" "ℹ️ " "Catched stop operation"
	if [ -f "/opt/bunkerweb/tmp/scheduler.pid" ] ; then
		log "ENTRYPOINT" "ℹ️ " "Stopping job scheduler ..."
		kill -s TERM "$(cat /opt/bunkerweb/tmp/scheduler.pid)"
	fi
}
trap "trap_exit" TERM INT QUIT

# trap SIGHUP
function trap_reload() {
	log "ENTRYPOINT" "ℹ️ " "Catched reload operation"
	/opt/bunkerweb/helpers/scheduler-restart.sh
	if [ $? -ne 0 ] ; then
		log "ENTRYPOINT" "ℹ️ " "Error while restarting scheduler"
	fi
}
trap "trap_reload" HUP

if [ "$SWARM_MODE" == "yes" ] ; then
	echo "Swarm" > /opt/bunkerweb/INTEGRATION
elif [ "$KUBERNETES_MODE" == "yes" ] ; then
	echo "Kubernetes" > /opt/bunkerweb/INTEGRATION
elif [ "$AUTOCONF_MODE" == "yes" ] ; then
	echo "Autoconf" > /opt/bunkerweb/INTEGRATION
fi

# Init database
get_env > "/tmp/variables.env"
/opt/bunkerweb/gen/main.py --variables /tmp/variables.env --method scheduler --init
if [ "$?" -ne 0 ] ; then
	log "ENTRYPOINT" "❌" "Scheduler generator failed"
	exit 1
fi

generate=yes
if [ -f "/etc/nginx/variables.env" ] && grep -q "^TEMP_NGINX=no$" /etc/nginx/variables.env ; then
	log "ENTRYPOINT" "⚠️ " "Looks like BunkerWeb configuration is already generated, will not generate it again"
	generate=no
fi

# execute jobs
log "ENTRYPOINT" "ℹ️ " "Executing scheduler ..."
/opt/bunkerweb/scheduler/main.py --generate $generate

log "ENTRYPOINT" "ℹ️ " "Scheduler stopped"
exit 0