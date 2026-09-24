"""Kafka integration package for CargoPilot API service."""
from app.kafka.producer import CargoPilotKafkaProducer
from app.kafka.consumer import CargoPilotKafkaConsumer

__all__ = ["CargoPilotKafkaProducer", "CargoPilotKafkaConsumer"]
