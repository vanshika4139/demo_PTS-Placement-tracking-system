-- phpMyAdmin SQL Dump
-- version 5.2.2
-- https://www.phpmyadmin.net/
--
-- Host: localhost
-- Generation Time: Aug 13, 2026 at 04:19 AM
-- Server version: 8.0.46-0ubuntu0.24.04.3
-- PHP Version: 8.3.6

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `demo_placement_tracking`
--

-- --------------------------------------------------------

--
-- Table structure for table `organizations`
--

CREATE TABLE `organizations` (
  `id` bigint UNSIGNED NOT NULL,
  `organization_code` varchar(50) NOT NULL,
  `organization_name` varchar(200) NOT NULL,
  `registration_number` varchar(100) DEFAULT NULL,
  `gst_number` varchar(50) DEFAULT NULL,
  `pan_number` varchar(50) DEFAULT NULL,
  `website` varchar(255) DEFAULT NULL,
  `email` varchar(150) DEFAULT NULL,
  `mobile` varchar(20) DEFAULT NULL,
  `contact_person` varchar(150) DEFAULT NULL,
  `designation` varchar(100) DEFAULT NULL,
  `address` text,
  `country_id` bigint UNSIGNED DEFAULT NULL,
  `state_id` bigint UNSIGNED DEFAULT NULL,
  `district_id` bigint UNSIGNED DEFAULT NULL,
  `pincode` varchar(10) DEFAULT NULL,
  `logo` varchar(500) DEFAULT NULL,
  `subscription_plan_id` bigint UNSIGNED DEFAULT NULL,
  `subscription_expiry_date` date DEFAULT NULL,
  `storage_used` bigint UNSIGNED DEFAULT '0',
  `candidate_limit` int UNSIGNED DEFAULT '0',
  `whatsapp_credits` int UNSIGNED DEFAULT '0',
  `sms_credits` int UNSIGNED DEFAULT '0',
  `email_credits` int UNSIGNED DEFAULT '0',
  `api_key` varchar(255) DEFAULT NULL,
  `webhook_url` varchar(500) DEFAULT NULL,
  `kyc_status` varchar(30) DEFAULT 'PENDING',
  `payment_status` varchar(30) DEFAULT 'PENDING',
  `status` tinyint NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `created_by` bigint UNSIGNED DEFAULT NULL,
  `modified_at` datetime DEFAULT NULL,
  `modified_by` bigint UNSIGNED DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Indexes for dumped tables
--

--
-- Indexes for table `organizations`
--
ALTER TABLE `organizations`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `organization_code` (`organization_code`),
  ADD KEY `idx_org_state` (`state_id`),
  ADD KEY `idx_org_district` (`district_id`),
  ADD KEY `fk_org_country` (`country_id`),
  ADD KEY `fk_org_plan` (`subscription_plan_id`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `organizations`
--
ALTER TABLE `organizations`
  MODIFY `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `organizations`
--
ALTER TABLE `organizations`
  ADD CONSTRAINT `fk_org_country` FOREIGN KEY (`country_id`) REFERENCES `countries` (`id`),
  ADD CONSTRAINT `fk_org_district` FOREIGN KEY (`district_id`) REFERENCES `districts` (`id`),
  ADD CONSTRAINT `fk_org_plan` FOREIGN KEY (`subscription_plan_id`) REFERENCES `subscription_plans` (`id`),
  ADD CONSTRAINT `fk_org_state` FOREIGN KEY (`state_id`) REFERENCES `states` (`id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
