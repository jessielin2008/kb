# Runbook: Fix Changefeeds error: `Message was too large`
## Confirmation Steps:

Following log line appears: kafka server: Message was too large, server rejected it to avoid allocation error  

Repeated failures and retries of changefeed backfill as in this case. 

## Resolution Steps:

There are several possible workarounds to be tried in tandem or individually:

Increase max message size settings on the Kafka server. message.max.bytes and replica.fetch.max.bytes are likely the most relevant settings.

If changefeeds messages are being batched via the kafka_sink_config option, try reducing batch sizes.

A batch of messages can be large even if individual messages are small, and thus can exceed the maximum size.

Reduce "Flush"."MaxMessages" or "Flush"."Frequency", which will have the effect of sending smaller, more frequent messages.

Upgrade to v21.2+ to capture improvements to repeated retries.

Upgrade to v22.2+; CRDB will attempt to dynamically reduce the batch size when this error is encountered, and automatically retry.

Backport to v22.1 pending.

## References:

https://github.com/cockroachdb/cockroach/issues/65211#issue-892176484 

https://stackoverflow.com/questions/21020347/how-can-i-send-large-messages-with-kafka-over-15mb/21343878#21343878 

https://kafka.apache.org/documentation/ 

https://github.com/cockroachdb/cockroach/pull/86138 

https://www.cockroachlabs.com/docs/stable/create-changefeed.html#kafka-sink-configuration 

https://cockroachdb.zendesk.com/agent/tickets/12115

https://cockroachlabs.atlassian.net/wiki/spaces/CKB/pages/2394554627 