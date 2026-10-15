-- Runs once, on first start of an empty data volume.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE DATABASE nimbo_test;
\connect nimbo_test
CREATE EXTENSION IF NOT EXISTS vector;
