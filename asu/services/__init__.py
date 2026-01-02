"""
ASU Microservices

This package contains independent microservices that can be deployed separately:
- prepare_service: Lightweight service for package resolution and validation
- build_service: Heavy service for firmware image building

These services share common models and utilities but can run in separate containers.
"""
