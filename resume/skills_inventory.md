# Skills Inventory

Every tool/technology Chidvilas has genuinely used. This is the source of truth for keyword
matching: a job keyword counts as "matched" only if it maps to a line here, and the tailored resume
may only claim skills listed here.

Format: `- Canonical Name | synonym, synonym` — synonyms are other names for the **same** thing
(e.g. ADLS = Azure Data Lake Storage), never related-but-different tools.

To add a skill: put it under the right category **only if you have actually used it**, then run
`py -3.12 -m modal deploy modal_app.py` so the daily job picks it up. See `keyword_gaps.md` for
keywords jobs keep asking for that aren't here yet.

Seeded 2026-10-05 from `base_resume.md`. 2026-10-06: owner confirmed hands-on use of MCP, RAG, dbt,
LangChain, Pydantic and Apache Kafka (added or already present).

## Cloud Platforms
- Microsoft Azure | Azure
- Azure Databricks
- Azure Data Factory | ADF, Data Factory
- Azure Synapse Analytics | Synapse, Azure Synapse
- Azure Event Hubs | Event Hubs
- Azure Data Lake Storage | ADLS, ADLS Gen2, Azure Data Lake
- Azure Monitor
- Azure Migrate
- Amazon Web Services | AWS
- Amazon S3 | S3, AWS S3
- Amazon EC2 | EC2, AWS EC2
- AWS Lambda | Lambda
- AWS Glue | Glue
- Google Cloud Platform | GCP, Google Cloud
- Google BigQuery | BigQuery
- Google Cloud Storage | GCS

## Data Processing & Streaming
- Databricks | Databricks Lakehouse Platform
- Apache Spark | Spark
- PySpark
- Spark SQL
- Delta Lake
- Delta Live Tables | DLT
- Unity Catalog
- Apache Kafka | Kafka
- Apache Hadoop | Hadoop, HDFS
- Streaming ETL | stream processing, real-time streaming, real-time data pipelines
- Batch Processing | batch pipelines
- dbt | dbt Core, dbt Cloud, data build tool

## Orchestration & ETL
- Apache Airflow | Airflow
- Informatica
- SSIS | SQL Server Integration Services
- Apache Sqoop | Sqoop
- Oracle Data Integrator | ODI
- ETL | ETL pipelines
- ELT
- REST APIs | REST, RESTful APIs
- FastAPI | Fast API
- SOAP APIs | SOAP

## Warehousing & Databases
- Microsoft SQL Server | SQL Server, MS SQL
- Oracle | Oracle Database
- MySQL
- PostgreSQL | Postgres
- NoSQL
- Data Modeling | data models, logical data modeling, physical data modeling
- Star Schema | dimensional modeling, fact and dimension tables
- ERwin | ERWin Data Modeler

## Programming
- Python
- SQL
- T-SQL
- Bash | shell scripting
- YAML

## AI & ML
- LLM Integration | LLMs, large language models
- Vector Search | vector similarity search
- Embeddings
- Sentiment Analysis
- Recommendation Engines | recommender systems
- Feature Engineering
- MLflow
- MLOps
- Scikit-learn | sklearn
- Pandas
- NumPy
- Anomaly Detection
- Claude | Anthropic Claude, Anthropic
- Model Context Protocol | MCP, MCP servers
- RAG | retrieval-augmented generation, retrieval augmented generation
- LangChain | Lang Chain
- Pydantic | Pydantic models
- OpenAI | OpenAI API

## Architecture & Practices
- Medallion Architecture | bronze/silver/gold
- Event-Driven Architecture
- Exactly-Once Semantics
- Schema Evolution
- Data Quality | data quality validation, data validation
- Data Governance
- Data Lineage | lineage tracking
- Cloud Migration
- Code Review
- Performance Optimization | performance tuning, query optimization, performance and cost tuning
- Schema Design | schema modeling
- Cost Optimization | cost management, compute cost optimization

## CI/CD & DevOps
- CI/CD
- Azure DevOps | ADO
- Terraform | Infrastructure as Code, IaC
- Docker | Docker Compose
- Jenkins
- Git
- GitHub Actions
- Pytest | unit testing
- Poetry
- Databricks Asset Bundles | DABs

## Visualization & Monitoring
- Power BI
- Tableau
- Splunk

## Additional Skills
- Spark Structured Streaming | Structured Streaming
- Lakehouse Architecture | Lakehouse, Data Lakehouse
- Data Warehousing | data warehouse
- Microsoft Fabric | Fabric
- GitHub Copilot | Git Copilot, Copilot
- Agile | Scrum
- Linux
- Data Pipeline Monitoring | observability, pipeline monitoring
## Confirmed by Chidvilas 2026-10-07 (from the Sheet's keyword gaps; see tool_review.md)
- Snowflake | Snowflake Data Cloud
- Snowpark
- Snowpipe | Snowpipe Streaming, Snow pipe Streaming
- Snowflake Cortex AI | Cortex AI, Snowflake Cortex
- Salesforce | Salesforce CRM
- Amazon Redshift | Redshift
- Amazon Athena | Athena
- Amazon Kinesis | Kinesis, Kinesis Data Streams, Kinesis Data Firehose
- Amazon SQS | SQS
- Amazon MWAA | MWAA, Managed Workflows for Apache Airflow
- AWS Step Functions | Step Functions
- Amazon EMR | EMR, Elastic MapReduce
- Amazon DynamoDB | DynamoDB
- Amazon RDS | RDS
- AWS IAM | IAM
- Amazon CloudWatch | CloudWatch
- AWS CloudFormation | CloudFormation
- Amazon ECS | ECS
- Amazon EKS | EKS
- Serverless | serverless computing
- Amazon Bedrock | Bedrock, AWS Bedrock
- Apache Iceberg | Iceberg
- Parquet | Apache Parquet
- Delta Lake Optimization | OPTIMIZE, Z-ORDER, Z-Ordering, VACUUM
- Delta Sharing
- Microsoft OneLake | OneLake
- Apache Hive | Hive
- Teradata
- Change Data Capture | CDC
- Azure Stream Analytics
- Azure Blob Storage | Blob Storage
- AzCopy
- Bicep | Azure Bicep
- Talend
- Data Masking | data de-identification, de-identification
- Data Vault | Data Vault modeling, Data Vault 2.0
- Scala
- SQL Window Functions | window functions, CTEs, common table expressions
- Kubernetes | K8s
- Microservices
- GitLab | GitLab CI, GitLab CI/CD
- GitHub
- SonarQube
- Jira
- Confluence
- SSRS | SQL Server Reporting Services
- MongoDB
- Apache Cassandra | Cassandra
- TensorFlow
- PyTorch
- Flask
- GraphQL
- Workday
