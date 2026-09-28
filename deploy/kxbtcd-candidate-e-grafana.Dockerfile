FROM grafana/grafana:13.2.1

ARG SQLITE_PLUGIN_VERSION=4.0.6

USER root
RUN grafana cli --pluginsDir /var/lib/grafana/plugins plugins install frser-sqlite-datasource ${SQLITE_PLUGIN_VERSION}
COPY deploy/grafana/provisioning /etc/grafana/provisioning
COPY deploy/grafana/dashboards /var/lib/grafana/provisioned-dashboards
RUN chown -R 472:0 /etc/grafana/provisioning /var/lib/grafana/provisioned-dashboards /var/lib/grafana/plugins
USER 472
