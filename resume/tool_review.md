# Tool Review: keyword gaps from the Sheet (2026-10-07)

Every tool that appeared in the Sheet's **Keyword Gaps** column, deduplicated (count = how many
job postings asked for it). Chidvilas marks each one:

- `[x]` = I have worked with it. It moves to `skills_inventory.md` and is used **on demand only**:
  it appears on a resume only when that job description asks for it.
- `[-]` = I have not worked with it. It stays off every resume (recorded so it isn't asked again).
- `[ ]` = not reviewed yet.

Reviewed 2026-10-07: confirmed tools were added to `skills_inventory.md` (section "Confirmed by
Chidvilas 2026-10-07"). Still open: the `[ ]` items.

Generic phrases from the gaps column ("data pipelines", "performance tuning", "unit tests",
"cloud storage"...) are not tools and are not listed; they never count as missing skills.

## Already on your base resume (just missing from matching)
- [x] 1. Snowflake (23) - on your base resume (Skills, Yana) but missing from the inventory, so every Snowflake job counted it as a gap
- [x] 2. Salesforce (2) - your resume has Salesforce API integration; add "Salesforce" as a skill?

## Cloud warehouses, lakehouse and table formats
- [x] 3. Amazon Redshift (11)
- [x] 4. Apache Iceberg (4)
- [x] 5. Parquet (3)
- [x] 6. Delta Lake OPTIMIZE / Z-ORDER / VACUUM (1)
- [x] 7. Delta Sharing (1)
- [x] 8. Microsoft OneLake (2)
- [x] 9. Snowpark (1)
- [x] 10. Snowpipe / Snowpipe Streaming (1)
- [x] 11. Snowflake Cortex AI (1)
- [x] 12. Apache Hive (1)
- [-] 13. Trino (1)
- [x] 14. Amazon Athena (1)
- [x] 15. Teradata (1)
- [-] 16. Sybase (1)

## Streaming and change data capture
- [x] 17. Change Data Capture (CDC) (6)
- [ ] 18. Debezium (2)
- [x] 19. Amazon Kinesis (7)
- [ ] 20. Apache Flink (2)
- [x] 21. Azure Stream Analytics (1)
- [ ] 22. Google Pub/Sub (1)
- [x] 23. Amazon SQS (1)

## Orchestration and ingestion tools
- [ ] 24. Dagster (7)
- [ ] 25. Prefect (1)
- [x] 26. Amazon MWAA (managed Airflow) (1)
- [x] 27. AWS Step Functions (2)
- [ ] 28. Fivetran (3)
- [ ] 29. Airbyte (1)
- [x] 30. Talend (2)
- [ ] 31. SnapLogic (1)
- [ ] 32. Qlik Replicate / Qlik (1)

## AWS services
- [x] 33. Amazon EMR (2)
- [x] 34. Amazon DynamoDB (2)
- [x] 35. Amazon RDS (1)
- [x] 36. AWS IAM (1)
- [x] 37. Amazon CloudWatch (1)
- [x] 38. AWS CloudFormation (1)
- [x] 39. Amazon ECS (1)
- [x] 40. Amazon EKS (1)
- [x] 41. Serverless (AWS Lambda style) (2) - Lambda is already in your inventory
- [x] 42. Amazon Bedrock (2)

## Azure
- [x] 43. Azure Blob Storage (1)
- [x] 44. AzCopy (1)
- [x] 45. Bicep (1)

## Data quality, governance and security
- [ ] 46. Great Expectations (2)
- [ ] 47. Monte Carlo (data observability) (1)
- [ ] 48. Collibra (1)
- [ ] 49. RBAC / row-level security (2)
- [x] 50. Data masking / de-identification (1)
- [ ] 51. Open Policy Agent (OPA / Rego) (1)
- [x] 52. Data Vault modeling (1)
- [ ] 53. Slowly changing dimensions (SCD) (1)
- [-] 54. FedRAMP / FISMA / STIG / RMF compliance (1)

## Languages
- [x] 55. Scala (6)
- [-] 56. Java (4)
- [-] 57. PowerShell (3)
- [-] 58. JavaScript (1)
- [-] 59. C# / .NET (2)
- [-] 60. Ruby (1)
- [x] 61. SQL window functions / CTEs (2)

## DevOps, containers and collaboration
- [x] 62. Kubernetes (6)
- [x] 63. Microservices (2)
- [x] 64. GitLab / GitLab CI (2)
- [x] 65. SonarQube (1)
- [x] 66. Jira (4)
- [x] 67. Confluence (1)
- [-] 68. HLD / LLD design documents (1)

## BI and reporting
- [-] 69. Looker (2)
- [x] 70. SSRS (1)

## Databases
- [x] 71. MongoDB (1)
- [x] 72. Cassandra (1)
- [-] 73. pgvector (1)
- [-] 74. Chroma (vector database) (1)

## ML and AI
- [x] 75. TensorFlow (1)
- [x] 76. PyTorch (1)
- [-] 77. XGBoost (1)
- [-] 78. Feature Store (1)
- [-] 79. Windsurf (AI coding tool) (1)
- [-] 80. Devin (AI coding tool) (1)

## Web and business applications
- [x] 81. Flask (1)
- [x] 82. GraphQL (1)
- [-] 83. Vue (1)
- [x] 84. Workday (2)
- [-] 85. SAP (1)
