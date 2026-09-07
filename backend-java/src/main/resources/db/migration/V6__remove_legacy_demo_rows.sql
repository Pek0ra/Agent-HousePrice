SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;

DELETE FROM house_info
WHERE dataset_id IS NULL
  AND ((data_source = 'PUBLIC_DATASET' AND source_record_id = 'SAMPLE-001')
    OR (data_source = 'AGENT_SAMPLE' AND source_record_id LIKE 'AGENT-SALE-%'));

DELETE FROM rental_listing
WHERE dataset_id IS NULL
  AND data_source = 'AGENT_SAMPLE'
  AND source_record_id LIKE 'AGENT-RENT-%';
