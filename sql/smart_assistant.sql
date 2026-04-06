-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- 主机： 127.0.0.1
-- 生成日期： 2025-06-11 16:34:06
-- 服务器版本： 10.4.32-MariaDB
-- PHP 版本： 8.2.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- 数据库： `smart_assistant`
--

-- --------------------------------------------------------

--
-- 表的结构 `admin`
--

CREATE TABLE `admin` (
  `admin_id` int(11) NOT NULL,
  `admin_username` varchar(50) NOT NULL,
  `admin_password` text NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- 转存表中的数据 `admin`
--

INSERT INTO `admin` (`admin_id`, `admin_username`, `admin_password`) VALUES
(1, 'admin', '1234');

-- --------------------------------------------------------

--
-- 表的结构 `config`
--

CREATE TABLE `config` (
  `config_id` int(11) NOT NULL,
  `model_id` int(11) NOT NULL,
  `general_volume` int(11) NOT NULL,
  `music_volume` int(11) NOT NULL,
  `power` enum('on','off') DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- 表的结构 `model`
--

CREATE TABLE `model` (
  `model_id` int(11) NOT NULL,
  `model_name` varchar(30) NOT NULL,
  `model_password` varchar(24) NOT NULL,
  `ip_address` varchar(15) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- 转存表中的数据 `model`
--

INSERT INTO `model` (`model_id`, `model_name`, `model_password`, `ip_address`) VALUES
(1, 'YumiDevice001', 'r2OHymFLSC6AvpjUXo4enC3Y', '192.168.247.24'),
(2, 'YumiDevice002', 'TBTdje6tT1cCXxt62JEKZVj0', '192.168.33.83'),
(3, 'YumiDevice003', 'qzFsXwpPOe1HeuQG2GJfXjMs', '192.168.89.209'),
(4, 'YumiDevice004', 'jsSSp7yKSOsPyDlFm1vjuYaz', '192.168.172.190'),
(5, 'YumiDevice005', 'gx5e1j4mVoXjhfeksQdMl4B6', '192.168.79.199'),
(6, 'YumiDevice006', 'qMXTZeDKwGCfi6CkQaCrvsva', '192.168.118.209'),
(7, 'YumiDevice007', 'uoZNNcEQ00KxpKBHqkz5jCrk', '192.168.202.10'),
(8, 'YumiDevice008', 'qvFrRXvo2IN2sEiBGYnnokfQ', '192.168.140.16'),
(9, 'YumiDevice009', 'DmTzl3U9pmW6EYrZlW39pw4B', '192.168.45.214'),
(10, 'YumiDevice010', 'oeHgJKj74j6l763KfPp7vzkH', '192.168.109.141'),
(11, 'YumiDevice011', '2PwN0wzYY8X8SOUukLBsnxPQ', '192.168.162.71'),
(12, 'YumiDevice012', 'WHKnHC0otN5hZzBAOrftdjZV', '192.168.170.118'),
(13, 'YumiDevice013', 'LDQfrUSbCw5Lqf1mhupf5E0S', '192.168.142.161'),
(14, 'YumiDevice014', '918O46ELHam8RbR4potuMbRZ', '192.168.126.87'),
(15, 'YumiDevice015', 'OdZJKleV8uP69yOmuaTTYXJ8', '192.168.48.106'),
(16, 'YumiDevice016', 'W7te55hns5CNqv3dWckhku2N', '192.168.82.19'),
(17, 'YumiDevice017', 'jVbCJiKQE21LGNLJluHsr1p8', '192.168.117.240'),
(18, 'YumiDevice018', 'JbCKvffwWjhYGpaVUeqYx8vH', '192.168.162.35'),
(19, 'YumiDevice019', 'N7N7dt7I6cDr025LtkahJESZ', '192.168.219.139'),
(20, 'YumiDevice020', '9Vw1zNkwMzKV4kScBK1hXDbS', '192.168.32.246'),
(21, 'YumiDevice021', 'rr9wPJ6XFOKLB1cyyLig5aLt', '192.168.230.249'),
(22, 'YumiDevice022', 'bxHnozV3Ki1gea802jAl3PoH', '192.168.120.246'),
(23, 'YumiDevice023', 'wAyfXbaRedIJX7ypNAbEX1nc', '192.168.138.104'),
(24, 'YumiDevice024', 'cRH30ZOfLQJySfSwvQaG8eS4', '192.168.110.41'),
(25, 'YumiDevice025', 'oyYO9QoIOCG4K3bxdfyk3nzv', '192.168.27.43'),
(26, 'YumiDevice026', 'ndSOmL3oLPcY1luPwt9NE6My', '192.168.69.238'),
(27, 'YumiDevice027', 'ucLATaLeYIe786e9hISHwTU0', '192.168.183.135'),
(28, 'YumiDevice028', 'SLmIRsw9R44CsGrrAKJ4s2lr', '192.168.11.5'),
(29, 'YumiDevice029', 'iAgSvA1LFvpBRdOOrdkVofNe', '192.168.15.186'),
(30, 'YumiDevice030', 'gOyQja3ENDpKtFTOcOIzdEAD', '192.168.79.97'),
(31, 'YumiDevice031', 'bcEsGwLbJ5kKrqwQVyTwrrRh', '192.168.205.28'),
(32, 'YumiDevice032', 'hk8zL9Vt2ztEN89SA6jt1rCx', '192.168.2.189'),
(33, 'YumiDevice033', 'qZrQmBdxLpuLCtYmpgGoQIIz', '192.168.170.157'),
(34, 'YumiDevice034', 'yME1STcyd4ATM5fcRmu40qMc', '192.168.28.143'),
(35, 'YumiDevice035', 'DYtEt6j8lIaH9qO2VrZSjKiO', '192.168.58.40'),
(36, 'YumiDevice036', '5Fy2AUFkn1QkPSGeGo1MI9A9', '192.168.243.37'),
(37, 'YumiDevice037', 'srmgf4IVg9Ev0SENXvPlkTX5', '192.168.120.93'),
(38, 'YumiDevice038', 'nhz3bye7KzlKIbjm8pZumjRl', '192.168.52.202'),
(39, 'YumiDevice039', 'WBQLhtOl7qIaH8L8satZqZYT', '192.168.39.197'),
(40, 'YumiDevice040', '1MAEMfLlykm3mSoYK71SoK6h', '192.168.226.46'),
(41, 'YumiDevice041', '3MjRe93AyLPPDXtNSptl0kJE', '192.168.252.42'),
(42, 'YumiDevice042', 'NwC9DvZAzqNwLFaVn610b21W', '192.168.196.143'),
(43, 'YumiDevice043', 'KhGmmIQfzKE5pgUii70blm4c', '192.168.82.94'),
(44, 'YumiDevice044', 'ZtpwsXcnENfpn1N7lRKzbXVd', '192.168.205.227'),
(45, 'YumiDevice045', 'PGVDgx4broGspVdvv0L2LhUu', '192.168.181.215'),
(46, 'YumiDevice046', 'ejMZqBzU70nJuK1Femjz4Ndh', '192.168.125.54'),
(47, 'YumiDevice047', 'Cgo4wyGjGVwh4OnrBOvQWgqs', '192.168.39.24'),
(48, 'YumiDevice048', 'wpOCqyEaxthwQTlhN7zcqJei', '192.168.1.63'),
(49, 'YumiDevice049', '7XusWF9vbYD429iwUixi8ImG', '192.168.99.180'),
(50, 'YumiDevice050', 'nB8BXOX2fINy3mTEmDtq7Apt', '192.168.23.144'),
(51, 'YumiDevice051', 'l1pXlOcjXPgSjXwDTZAiL4mp', '192.168.107.212'),
(52, 'YumiDevice052', 'w5MqmOXAfaAmKgiIUaU5pGUD', '192.168.28.25'),
(53, 'YumiDevice053', 'Zf0up2CrNCrnyndo163EpWxc', '192.168.110.224'),
(54, 'YumiDevice054', 'gVGou5t787WHcbGwwL0eT4Ih', '192.168.234.189'),
(55, 'YumiDevice055', 'D87y3nDPdl0UZ667v5jP1zRl', '192.168.4.8'),
(56, 'YumiDevice056', 'WTYHFaj8CW2Yxfi2FWc80ioZ', '192.168.168.36'),
(57, 'YumiDevice057', '6DlEfFHYwpXoq9pZWZ2vbnyJ', '192.168.129.129'),
(58, 'YumiDevice058', 'wh1hTFm7k6aWFCZUiRB9zU2o', '192.168.110.149'),
(59, 'YumiDevice059', 'pIBwfFGQUY1164qL9DrTiFf5', '192.168.42.36'),
(60, 'YumiDevice060', 'YTFsLu3uAK2cE2wrejAHQOoE', '192.168.146.247'),
(61, 'YumiDevice061', 'PpGZZLXD3w7EPUMYHJH7gQpt', '192.168.115.47'),
(62, 'YumiDevice062', '44EFI3HiccwOdng47ichmyom', '192.168.232.160'),
(63, 'YumiDevice063', 'YeYgWMMOHBhoJld8Kc8N5HGj', '192.168.43.9'),
(64, 'YumiDevice064', 'cIBjPdbsAfEDFOTsj3cRzEoI', '192.168.66.43'),
(65, 'YumiDevice065', 'uPdeCUK0qmcfSJOP6UIS4bxY', '192.168.120.81'),
(66, 'YumiDevice066', 'tJpneix96xCZZorIyko4sxuQ', '192.168.222.94'),
(67, 'YumiDevice067', 'MxejBlRKVWhbB6jRMOscvTmr', '192.168.79.71'),
(68, 'YumiDevice068', 'q85ZVv7Au0qRVcfgS0pOLuq3', '192.168.96.55'),
(69, 'YumiDevice069', 'v5zixsatP6anDiJyixWPTzRh', '192.168.99.14'),
(70, 'YumiDevice070', 'R178c65jdKrlWbN8JRS6Yjwk', '192.168.137.117'),
(71, 'YumiDevice071', 'x71AY2KNBx3C2g5j4LzJZaKt', '192.168.16.133'),
(72, 'YumiDevice072', 'mRQLBAzIMxaETLpYxQlieKip', '192.168.161.4'),
(73, 'YumiDevice073', 'dbLCCtUu3YZ7yLh4LhJap0a3', '192.168.168.50'),
(74, 'YumiDevice074', 'p1aClile7hyWcnVgvwTgcInF', '192.168.188.127'),
(75, 'YumiDevice075', '6aRcD3KuwubAoxsvAsUKLWD6', '192.168.35.25'),
(76, 'YumiDevice076', 'XCOBLp4kv29QNW13HZCTTLSP', '192.168.127.222'),
(77, 'YumiDevice077', 'datuO6vXTE4mioQvTgzwexcW', '192.168.250.83'),
(78, 'YumiDevice078', '1OHcjLdLVpHku2q3aDxjX8mc', '192.168.64.107'),
(79, 'YumiDevice079', 'e61djt6h4yvNeGBtJjb331tm', '192.168.128.25'),
(80, 'YumiDevice080', 'QTEqspQ6JwmRWsl4UKT9sMSc', '192.168.140.244'),
(81, 'YumiDevice081', 'TD2DDPky3kvw4u8SvJAGIcnz', '192.168.98.80'),
(82, 'YumiDevice082', 'TSveyoS6fTKPJxX0t88mpYeA', '192.168.82.15'),
(83, 'YumiDevice083', 'EaAXw5HZs8B6clgGSXl6R3lI', '192.168.36.250'),
(84, 'YumiDevice084', 'deVJJTZA0P1PhxWS9gerpeoy', '192.168.38.70'),
(85, 'YumiDevice085', '3MwZxdFWBPd6WHj88ycRJhgU', '192.168.142.182'),
(86, 'YumiDevice086', '8zmhwipEcQoK9nyewqJX9bN0', '192.168.209.24'),
(87, 'YumiDevice087', 'QbcTS5Nt88eebZFzESKv78eD', '192.168.9.192'),
(88, 'YumiDevice088', 'GYpdJK018q9B2Ti3ilfEONQ6', '192.168.190.177'),
(89, 'YumiDevice089', 'jYqG0tZQGrM3CCUI7x2kRh7X', '192.168.132.159'),
(90, 'YumiDevice090', 'EAZiqMZXwxnN7dnPXMFeuHi1', '192.168.53.26'),
(91, 'YumiDevice091', 'sMO5V2gZWPIMoJ7rF4GHyqSX', '192.168.177.151'),
(92, 'YumiDevice092', 'MsJ6abKA9aIrpBz9pLtdHj1D', '192.168.239.34'),
(93, 'YumiDevice093', 'KirevHNnVnx3I5zcoiE0VCkO', '192.168.48.102'),
(94, 'YumiDevice094', 'oqRe1CBE0HvIZfItYw2fXMS2', '192.168.35.15'),
(95, 'YumiDevice095', 'Vy0sNoQ3L6PCFsax0zvkYcug', '192.168.23.143'),
(96, 'YumiDevice096', 'TtwuUyK8bawg8IjvYamIDDOb', '192.168.170.86'),
(97, 'YumiDevice097', 'uIjxs8WGS7kcs5Nt7Jtn3mCQ', '192.168.161.104'),
(98, 'YumiDevice098', 'cxRE9vjlxVJT33OoUWJDfPpa', '192.168.211.5'),
(99, 'YumiDevice099', 'EFTx6lBWMKSfJQ1RjO9AhBpM', '192.168.34.121'),
(100, 'YumiDevice100', 'X4OYo5XYmtpHTvoIjfwziaej', '192.168.131.48');

-- --------------------------------------------------------

--
-- 表的结构 `scene`
--

CREATE TABLE `scene` (
  `scene_id` int(11) NOT NULL,
  `user_id` varchar(10) NOT NULL,
  `scene_name` varchar(30) NOT NULL,
  `general_volume` int(11) DEFAULT NULL,
  `music_volume` int(11) DEFAULT NULL,
  `auto_time_start` int(11) DEFAULT NULL,
  `auto_time_end` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- 表的结构 `schedule`
--

CREATE TABLE `schedule` (
  `schedule_id` int(11) NOT NULL,
  `user_id` varchar(10) NOT NULL,
  `model_id` int(11) NOT NULL,
  `timestamp` int(11) NOT NULL,
  `content` text NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- 表的结构 `smart_home`
--

CREATE TABLE `smart_home` (
  `smart_home_id` int(11) NOT NULL,
  `model_id` int(11) NOT NULL,
  `smart_home_name` varchar(30) NOT NULL,
  `smart_home_status` varchar(30) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- 表的结构 `users`
--

CREATE TABLE `users` (
  `user_id` varchar(10) NOT NULL,
  `user_username` varchar(50) NOT NULL,
  `user_password` text NOT NULL,
  `user_email` varchar(50) NOT NULL,
  `user_tel` varchar(20) DEFAULT NULL,
  `user_avatar` varchar(255) DEFAULT NULL,
  `create_at` date NOT NULL,
  `user_status` enum('enable','disable') NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- 转存表中的数据 `users`
--

INSERT INTO `users` (`user_id`, `user_username`, `user_password`, `user_email`, `user_tel`, `user_avatar`, `create_at`, `user_status`) VALUES
('user001', 'Sagiri504', 'scrypt:32768:8:1$tooHK0NOyUvJDLCP$816d8b67298bc16c8e03f230f36fc3567967e49d75cd01b49bca2e0f187f21aab37be8301b2ffed8fed6efe5bc9629f43fff75252436f9e479414f4b4da426ca', 'chenjunxu6862@gmail.com', '01157768208', '/avatar/user001/1749140210_kurisu2.jpg', '2025-05-06', 'enable'),
('user002', 'GohWT', 'scrypt:32768:8:1$uBR1QcW7iSUbgT9n$60cf005095c1f1bd5457f743431d800ca08af0687e87d8db504f7427147bd506982ef223c4312f6e7341da094008ffd4f28e11fce199286e25afdf41fda36ad7', 'wtgoh1001@gmail.com', NULL, NULL, '2025-05-12', 'enable'),
('user003', 'testuser003', 'scrypt:32768:8:1$4j258J5aQ9WQZUxS$e9a6ecaaf7cfd68e57593e19aa77f408a4a84893f7b498acb3264f07f588d614375b7120c0f18ba0f55b7a9fdcb03dace74b28f6e2f42a9652ba17901e1b7578', 'user003@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user004', 'testuser004', 'scrypt:32768:8:1$fKx7cTXKiNPOsyAm$93e7e6411293e2272b5f115d2f35e9afef8b487bca8c936a9298dce58164af9685b19f1c3fa18f1ffa4c9d4c70d1446c0abec30fdf180313db7b0893bdf19d35', 'user004@example.com', NULL, NULL, '2025-06-05', 'disable'),
('user005', 'testuser005', 'scrypt:32768:8:1$9z8Ss7t1LE1NvXay$44fe7f008b63f0201d1e3b7a6ad2756750b332d6df28441a79ad5d769cdc4ddbd4c9a8bd0ced19e4cfeedb5837d7149518710f15ee5464e1742d3102214d7c36', 'user005@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user006', 'testuser006', 'scrypt:32768:8:1$ghQoAnrOxBM9rNyT$df299529fc8c7e649bbc82f4afcae508df75a5a0381b789e9bf51a039966e194e0328c1c1726f7684601f936b86475111817573f08e89366e875ff91f7450180', 'user006@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user007', 'testuser007', 'scrypt:32768:8:1$OEMM2SvgBd5Q0nHN$8e89153f4f54e080ab02b1bad778a2359848adafb537522e0f9c559e12271e7cb9840bcd67d3a99b1c9d3c51de2fd01aa705bff263c0eeb040ef75730084a3a4', 'user007@example.com', NULL, NULL, '2025-06-05', 'disable'),
('user008', 'testuser008', 'scrypt:32768:8:1$jrpzEKWZk5a9hNPC$b115142e484eccb983bf1e6480ff11cc5e9153d43eb4c6a77468a73f23754b4ad44f60d5377019b67922330a2fafa66f95d47b3987fe48500f52826b8f19a77e', 'user008@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user009', 'testuser009', 'scrypt:32768:8:1$itAbTVQqfx9rhES2$3080c3bd6fc358c26fcca8e45a6c7f6228564f2223748cc19b75ffc6451e054e3afbe32bdc833df31ef0c3b09d2e549bb987d77deb002fb8611049b2ac49f6ec', 'user009@example.com', NULL, NULL, '2025-06-05', 'disable'),
('user010', 'testuser010', 'scrypt:32768:8:1$qTBL03LZixxj8JNh$940e97b6212542ba36a7e5f83b2517b0139672b2c0ed23cb91cd7f9b055f47c85a55dd2665726a6f7828d4b7bdc27f2795b4d58ca96f8ba8e5c543bdb037bd1c', 'user010@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user011', 'testuser011', 'scrypt:32768:8:1$sOhfCGYhEGNXgA6p$bdba1043f66ca9b5a7af160a75ee907cdff7950f1051e766ac9ef4336ca34503367d9bf3a174e5b0bcec5d5dd1d69a644785bc398a388113e731642396ef81b7', 'user011@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user012', 'testuser012', 'scrypt:32768:8:1$dvOS7mEVVglpoaiO$ec03d630fc76631f2f33180939378ca327e82ee83d736ede8f51c9512351d342de9238709910cf24385fbe12bd4f7175a3494a2b7997d515410a895ae2792227', 'user012@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user013', 'testuser013', 'scrypt:32768:8:1$6QBtpzTw7mPWREPw$24ae9cb9a75b853c9f4bede4ed3cdb782636580c20f4e60e9d48529d0fbe54be3d3e08bb3bd1e0993094f18c61ff32b3c3722fee2596a246f3f2c85cdf5249db', 'user013@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user014', 'testuser014', 'scrypt:32768:8:1$WzD3W8uqeFmnxjsI$9acdbc98ce819dd9e7e5b33760198d1aa3e33266f46713eeae61f51eb6e19913412c839cb224853d93aeefaa013887896e6a28f411fec18fc15b3ea9149db1ac', 'user014@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user015', 'testuser015', 'scrypt:32768:8:1$hg6ddjRtmErdqXJ1$222aa97f02770c8de5d8e26e27c6284249c09668bc04b7c27280362cd34224c9fe7fc981603289871a451d24797e3b6519d4c559cde1d90489c03042baff9c69', 'user015@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user016', 'testuser016', 'scrypt:32768:8:1$dOksVmZHN6PfvR2P$c4b4789c165963f5e28053307d3fc3728daaf6daff1f3c2e65af299314f425d7951bf51dd0a88faabcfd14847d19db9904fc21a3150fef21109a59d388b55e4a', 'user016@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user017', 'testuser017', 'scrypt:32768:8:1$Q5VE6oyoLaET9B9g$a516116a329a3698a3c36696403c509181bc4968435c0831c3f9512f171c8575ee3bb73f301c1a88aa669464da1838888e4ea7b813fca8780defe8b6834c5308', 'user017@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user018', 'testuser018', 'scrypt:32768:8:1$q5QsmAh9id0vvYlC$e3892957be98d4508e9f0e64512701213a969dc05953ac8fe639dcb258f0fb66ce9fce0bb21142fb2ab57d59c1f43f974374f80b1ffe95e89db176d47e4f3a00', 'user018@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user019', 'testuser019', 'scrypt:32768:8:1$dGQanBKkpqTu94hU$2e1d7cf8241ba3c51675e444e3f6df9bd160536092d06e5dee4ddab3206b5ed214e0d8cd9e2c271aa627d27321933c546c5cd19b53dfaafef63b0e760085f11b', 'user019@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user020', 'testuser020', 'scrypt:32768:8:1$OrkScH00MvtpLZKP$d0f20cbebc9ce129e850a932a8cb6a5fa90196b6b2fb1f645a3d05336119a94db69ea2d98402265429ca6a403112785151913ff694eaffe9e310527c9664ba3a', 'user020@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user021', 'testuser021', 'scrypt:32768:8:1$r72R5bAo0jbs6R9N$216f751be639660ae79abc0628450ef7a5e8b888802449df7eacfc06f410e9a9a7b249f9dbdde25ae46932aecdf39d4059eef0acb1cde264ecb6aa982d4d0eb5', 'user021@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user022', 'testuser022', 'scrypt:32768:8:1$HK8vyEl5Fqrlqv9J$a57d26dca873db6c04990bd05f9ad16484700b54d75fdee864ef5973d097d057a29b8abf2602fc49ecab3fe635edd59fb4ba977b4123928e2b2b092f7df58daf', 'user022@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user023', 'testuser023', 'scrypt:32768:8:1$z7P3OgaZiD8zTr85$efda4d210ecf233287481a72c20f4d9a5966773bf951341510092b8e8d915215f1b5f118236bd83035a3134c75cbf1455f983a05161113289995afdf3ebdb31e', 'user023@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user024', 'testuser024', 'scrypt:32768:8:1$UhhiSlp9ysPCNEvQ$3a45918ae1e5574a45bf84e8c819715c8579cd79ad57f88298c23f1279388c07b2e230517a408c0dc698aa8f7fb2ab0612c6759df751130df0c68949f1b21926', 'user024@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user025', 'testuser025', 'scrypt:32768:8:1$fyAYNghb33SnTcdg$b8d7c63077ffac6e33e04dd8c219d6d153947a11144ccd6d0a9b3922badf599ee2a814873516f6520987f317b7b874956e61b496930c6009fad59a1a5d2cab17', 'user025@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user026', 'testuser026', 'scrypt:32768:8:1$4wLqjBv0EjPB548y$857deeafe44841ee3ebcdd52943330675d4b4f0f686c5eb4df7953cedf480c770119b468c566300c1259999c7d42d37e1e8fa75c14c79d3e64c59abf8acd4775', 'user026@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user027', 'testuser027', 'scrypt:32768:8:1$9rR1rnPesuTXHVZH$84a98b0b24ba1e308493dc71f0660a390d5830f82ee160018895ce18c544772975e5b37a6838c05ae788e5f1139ea19f8e6b4155748966516b4d0a756e0560a9', 'user027@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user028', 'testuser028', 'scrypt:32768:8:1$Fsqv3X0fCZPJIWBO$7fbe6bd0a5db5bd8f3f7a517ee2e496cd0f978a67585138e473c56c7d03a664f8c978c137d656a5dfae33a4e71d0c764e223dea18c7e60f0c7819ebf61954110', 'user028@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user029', 'testuser029', 'scrypt:32768:8:1$0eyT0lzhC83kQtYB$3f3f00068c6554989aceda9de2992ea31584bc16ef295c1bc17b3f9d06ed35b3b5b4ade7f70ba92f9e9a96f5ffcc0a9e92146670650a65fd122db2c41eee74b3', 'user029@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user030', 'testuser030', 'scrypt:32768:8:1$MKrI42QiqSWOzthj$09db8fbf86dfcb2f9b35d1c3075911b5e07c0db0086c259f5dee41b36a65d75c91b9b6687f7d6111993e7f4e0e7f870153c55a34f6d8bb3a1143d9488c3dce51', 'user030@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user031', 'testuser031', 'scrypt:32768:8:1$MvEJRTkiMB3p43ng$3a58c8a5d760d2c5e69d5c2ca473361997269e8671ed9d1c6feb5ae452afdea7c2acb1b0d6de03f8d5c6f3b1fb21976fc68d726d87e1e606e36df2306f35703c', 'user031@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user032', 'testuser032', 'scrypt:32768:8:1$i3J8AR681f7gaYMg$4672a19f0b28b6bd74cbf17e02cb77812c409962c5a4fb60c1abb2310c99ba63ec432f39cd4d889f1d716253db02b88eca6750a85dfc3ff4e89c65cb9b4880f3', 'user032@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user033', 'testuser033', 'scrypt:32768:8:1$GoUrLuDHcUfEkdPh$b31dcfccde2f4d999cf9fec9ecce3c9d7b3a8188ee4b988b32bf0a8773439ba59e42cfae60038f498b1e084a1e05a507540be08c9222d8a207e20e12213652ca', 'user033@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user034', 'testuser034', 'scrypt:32768:8:1$IfWrfVCZ5hlMIHtf$de58d267fb8ad1fe8a56af1d6ae4a02af04ad437493234d9461a6e978295da01e4784b3f5e1d7a091ca5200ba38b31df8c5033dd4512bfdd7d0a7563bd83dbf2', 'user034@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user035', 'testuser035', 'scrypt:32768:8:1$vE6TdRzhPhZ9D1oq$08740e5bd3afdaaebe5847d4e50f78c44ef2bf55de6f83aefe13eed2aba716590644f40dbba755048a5820a5d352f567b7ffaa61d7d6d2c010c6996c0b83e3a7', 'user035@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user036', 'testuser036', 'scrypt:32768:8:1$wjoP2z5wa7KBbHnU$f3e10b40c8d56bc7b168ccbb7b62717819503163ec61db470e8529d92566da519f058cb2bc50597f35d74a5033614544fa5d013f73e282a18d39676f5c80a7f8', 'user036@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user037', 'testuser037', 'scrypt:32768:8:1$C2V4ZSyrE5xf3fIm$044845a0cdd0b15a957b5c2eb84b52bdbdc3ffb06638862276a67c0e9f95e7b6d5ce9756c81f2b0dab0e561a3a3ee138ab7eb65d6e6f0fd60faf43f96930e10c', 'user037@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user038', 'testuser038', 'scrypt:32768:8:1$AAQfDh4Ws4jaQQly$056b571d5bc51cf4ef17894a036fbf8eda1aae0a8c2574ba4e5bbcc7ce90408612cd5bb1c37bc2e80940cc9fc6209376ecbd594aeb9eb8196b85ab270fd49ecf', 'user038@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user039', 'testuser039', 'scrypt:32768:8:1$nq7SHnO5YTFdQX2L$fe5c1bb2410e83a26dc095cc0f508d268039a76d1f79999fad6a06ae1ee551b67257f04df0b96dd0ca0f3b892ee95a6ffb3875f6011bd4b23fa79f9cf72890f7', 'user039@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user040', 'testuser040', 'scrypt:32768:8:1$E29QZykSZaWlT3VJ$2bda7be2437c684443371a585ca0ba7d9af30a6d1f2cd5cc5d19109c7a8590da95eee6f492a31e7b23abfcdc7e4bd120851d7be1f25f24a4c8348610b6417eee', 'user040@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user041', 'testuser041', 'scrypt:32768:8:1$13MzugOljyr30Xt0$264a9b60d791c6ebbb726e06cd1fa5671354861ac73054a2204ef7c58e1ed9920038057f6f98ccb24bc7da7fc224734e071433d8c52462e67a1b976bd2cf25ed', 'user041@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user042', 'testuser042', 'scrypt:32768:8:1$Xf1u7M1cBN61yGkQ$96492672b570df74b0dc13c6e82e18fdaa9bdef451c98584a9294d700202e164363f5412e0a07cfa293e69979421382d37bd04568a92a03cd7f3e7edb49e8ee4', 'user042@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user043', 'testuser043', 'scrypt:32768:8:1$u6XtBkSX4slP06xR$54c9eab89a54260c702ee4b8b3a8f304ebd486f528d7dd9491dcb4eaba2601b7c0d236ca9b3bd00fb5f8877ad20e00d50004c120c5f269f91eddc3d52ffc7397', 'user043@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user044', 'testuser044', 'scrypt:32768:8:1$2ZvwT2hgRxxkrris$aa7119a98dc15cd82d123905ff6081419aefe06d81067aac8a199736fe8c1fa9d6fb9ff008bf48c6a87bacd7a002d199d8a517a561fbd4c5ff0b46d74456348b', 'user044@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user045', 'testuser045', 'scrypt:32768:8:1$yoVXzn1BhemTWqUu$2458dcb0d44a469d529be18ca947ab04bd1e6b5d46732fb429ba571f69908e578b932945093e5a5103e84709d1e1541a97496ed866005a35f70e2df7a423bc26', 'user045@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user046', 'testuser046', 'scrypt:32768:8:1$Lu6cdPrn5JtgFXGw$9d0ff702f9a2622dd28cd866f98643e0800b87ae2aafaae52c5ae92e0c4eec431b35c7d533e9889509ea232a87b65145a01513ae4a199643df1aa041bd830967', 'user046@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user047', 'testuser047', 'scrypt:32768:8:1$mD21coxD9h6cH1ha$0c7f14978ab93a223a10592b469016b249d62c5413d046a6c8b1bf2edad9ec45e44f9b6ef76dd23bd522349c4e7fb8898c890ac80258d067109e7788e277c045', 'user047@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user048', 'testuser048', 'scrypt:32768:8:1$bdfH7OieBPA1JFuQ$c73f544c0e91d6c33b6cb072dd2de0d9a3e33ad18fc7b31e3afc34466b52cd29dde2fab3c06b61a76c6d19d2a12aa53200e8e77277c15a9660d0794baa4ee575', 'user048@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user049', 'testuser049', 'scrypt:32768:8:1$WoAkP4D8WzMm2Vmb$840f3f7ee9dcb97ebf477a0c55b207a82ef0be211d4bfc85b8198adffe0f41d54dc36780ee62120e57be9a7b0f74e4289345252018c71b49cd6f8c38dcd8e11e', 'user049@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user050', 'testuser050', 'scrypt:32768:8:1$oj66G2vQXg3RbOnA$57becabb7bc354a2d8ba8404b27c933017f6cfb2535eb6b8ce65b31a8a9dc0d83a043b7112724f474f9cd1429645f4cd82f4cec9745b103968e05a28ee18b554', 'user050@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user051', 'testuser051', 'scrypt:32768:8:1$GCL1Ye4Vph0vZ6qH$60ba25acdd98ad8867cb11d92537b31c114ef02edc3f3dced66152d82fbb539812503b16cb09adb56e8eb7d6e609a4e04ffb7a54d975bd2caf6667a4dd5a117a', 'user051@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user052', 'testuser052', 'scrypt:32768:8:1$VghA7EWNmCotsx61$76c848bf3dd85140de59b987ddb5de51ddca8cffd0c4454c851a29f2e58a8a0ae2325155f7529537ab561941a9ab5711ee2d98dc0c6b29ebab1a22c99fa75b11', 'user052@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user053', 'testuser053', 'scrypt:32768:8:1$LMb5Zz40SsDGg9Aw$725ec8f57aaf7b62ab1b5e047e9a02fe9bf7a2f7e0c682a9b42f3c4ba1d9d736bcbabd886691ee9de7aa41d653b7179d4746372e4ff32a53dc155c03a1e49115', 'user053@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user054', 'testuser054', 'scrypt:32768:8:1$fr9vvVLs0fFNF1j8$8d3f231c0d5ab4f127e46e60cdd8147e68857415baf810d42c789626f2f1ab289bb773c617660481d09e7ee48a01f43032075e4181c83eec241cdf92375682b2', 'user054@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user055', 'testuser055', 'scrypt:32768:8:1$RVME1s28Djyos35e$c0ff774da1a4f5825a440bc58ff65282c79861dfcab2b3beabe32675263f84ace4303eee7435fbc326af30c30268a4fe10c7a95aa3c2f2a849670e506ade1ff9', 'user055@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user056', 'testuser056', 'scrypt:32768:8:1$XF0G4aRbbIy64dcj$9e1549f8ca0fa6ac0294b20be089d116b292d1d9e3e70c07d24d7c710258a1d36153637fbbf370772c7318dae740b4925ebcddd29b4a8baddce0f8c17907b973', 'user056@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user057', 'testuser057', 'scrypt:32768:8:1$JKO2LVS8vE4mCMl5$aeb374d47f355717d062d06c02b9bccc6bc37bf8a536be5658a944b554cf7230cefae53a164c99fb20189de061d987e69c183d0d0680355b9755bce11bbd21b7', 'user057@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user058', 'testuser058', 'scrypt:32768:8:1$Ddk3C3WDAI9zIYsl$774277594a15338d6e4bfc1744061c6211448ad2eeb13e31f05057544af698d6f51db5ad70d1bd84f648a05d95986b2b53cde44551d935d422c9bf522fa0b779', 'user058@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user059', 'testuser059', 'scrypt:32768:8:1$baKX27L3EpkoJ0TS$cd983b21d5b62bb856b66f8bf669d98f5c63a4e477d8710b0419312f3c4c9db52a9da5996c0478b6ae9a6c81e59c0da06a20636beddd4dd678d66a56168429a4', 'user059@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user060', 'testuser060', 'scrypt:32768:8:1$ZN9PdayI0dvdOZcp$52fd45c9f4505144bfe2cbaaaa657f260e37a41724dd6bd6584e8ee6247f13e307feee726a6e3184cabe951f45abfef004a32340a975f4014191e35f6d577745', 'user060@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user061', 'testuser061', 'scrypt:32768:8:1$V1u8IxpeWoB9OZGn$4bdac5a387694ab915a0280ce96c709f0b6bf9189a584f275f1b01ed7e902a4a7c809a2b6425f09481a8f65c210210c3b678aa692d77c5aea05690c65bda2b8f', 'user061@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user062', 'testuser062', 'scrypt:32768:8:1$tKtdycZLGBTLdJh3$59973f317231d2f6a272d36df5b8dda04e311b548558fa31d4a6d493be5fe06ae94206dd84a9b6e3926d83ab0e7d3d986ab36844540f4f9b2ae1dec33619ab6b', 'user062@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user063', 'testuser063', 'scrypt:32768:8:1$QgQGKLsGWrE6mOa5$a6b3e559d2e613590d99ec15581a227260e124b5e260c2ccabd04554cea6e2d438fc80d0242cd8112b5a5651b63898f31ff974701865986f14440ed056cfe677', 'user063@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user064', 'testuser064', 'scrypt:32768:8:1$6tWdfdtfDejZ4s4H$b936a8a6175e9c78d03d846afa9787de063f8e3ac3976a37883498cffac2b4b9ff2537ecd75a0d73ca614ada397a5eee774405253c8837724e686ed425b990e4', 'user064@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user065', 'testuser065', 'scrypt:32768:8:1$gsPAaOAXbHF7twp0$04942192ea8c9c2e002802a82aa91a1b5324aa82be0025580be60c1c5e615c3096225274e8bb2c51796e409d51250b0ff473ed7effcdf051425e704e54fdabb5', 'user065@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user066', 'testuser066', 'scrypt:32768:8:1$j5sh2lyatzten5Z2$f5e56ec16f3f15920d9ccd4302788ea5c37001bfc992382204f9e769b1b730c23f9e88db50ee80bdf34cf48cee14064dfbb82e549cefa442d4f33702aea3ebc3', 'user066@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user067', 'testuser067', 'scrypt:32768:8:1$MfCnH0XHNuKaNFcj$0da47620a46eca14fd45189d47ea957be414cd74e01b35aa20a7e0b71928a9715b52f546c5bec26113b8a728676ab7959c9d4fdf021899182c3447b688a98310', 'user067@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user068', 'testuser068', 'scrypt:32768:8:1$ts1fp6la8I92urmc$096b54a661ef4eef192807dedd8b3071ff2094900c83a961bef0e9630c910580169d874502f85a72d96731fb0a11202cb7b9076af636706ad57f7c1e4a65532f', 'user068@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user069', 'testuser069', 'scrypt:32768:8:1$Zf180GyiZj511cEP$2e1dd876d34608aad0a309c38e3f2382f45c805ec79dea3d43e1d45be7e4b54ace91edaee69de4867448030cb3502cca1a1c97d3eb325c55fbdd7889fb2dbefc', 'user069@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user070', 'testuser070', 'scrypt:32768:8:1$BegNGJharfUR9Pb2$106f1b7043d5f0db20984550c8fc045c981618a82be25d6a0e2337c496e67e074338c150ac122b789b191db3964d8cb1f54ca16c7a0101c886a7d44100000027', 'user070@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user071', 'testuser071', 'scrypt:32768:8:1$Yn4ojdLLZRK5oZY2$325e7a5bc51bd043596a08c27a4950647558731f04c74534d9ec7291d27072b3b6e572651c40c1dc598c47c3119b37da35fcc93e111e0be256d609ce3a66e3e4', 'user071@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user072', 'testuser072', 'scrypt:32768:8:1$s2vr9QngJGLgl7k2$b368aa36757eeb80fb0e0e3cb6478d2c8f40c062e23fd5486845cc425ff5bad8f96703110d545a23922c245ecce05ec8fef6f87b196ad29f5614667f39524845', 'user072@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user073', 'testuser073', 'scrypt:32768:8:1$kAsP1CJcf1lbNCqW$79471e995d3a616fa240f2a9a4c036c8b95a1fcc43bad2833ba944c59ca19f9444432555a4a42bf876ec0496f38abd20b2a75ec2a06d2b93ae9e67e8875683ef', 'user073@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user074', 'testuser074', 'scrypt:32768:8:1$CBbqmYsQHub9lYcZ$a265552e729d5a5b2a332a949c717adfb03b86619eee3ca758098aaf68691426e88c4d2afbb44d802d09f86387ce5ab817e8e672b32d1604fdd687674f6c7a7e', 'user074@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user075', 'testuser075', 'scrypt:32768:8:1$yn0mmTYwUhscy52l$47505232ab621a0288737d464acbd6f9b153523f5d337df7b91de8251e470a547545bff6ba0dbeb498bbf791c39eba429f143df07f7727b4849fece3fa82398f', 'user075@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user076', 'testuser076', 'scrypt:32768:8:1$c0b2ZYDwsvDOplqD$77a509b6116c39658add64196d34fcead042e12f35dbbaa3170dc46604f368ca78186a4c54ae9af92be7c6422cddf6e0a9d77d0177cacfef29c1c87a121d0bf2', 'user076@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user077', 'testuser077', 'scrypt:32768:8:1$8xydOuYPj9lcEKYy$c75928075e586890fa996c4036ad56e56bd0b083c5ccce12a83d1c7cbe5844ba73241ffa143bf1e255f2a6c79edfe1e75939f26829525554c73eb2b39c78fc81', 'user077@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user078', 'testuser078', 'scrypt:32768:8:1$LQwBBc2h0NgvNBj5$3951714e4385c0f50796571ec28eb6c88f9a5cb8fad4dc7c834c0ffe30dd10e8035bd97f3a2e68346b9de2f1d09e2c957fe63d142fef5b4ec4175dd6c56f2e28', 'user078@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user079', 'testuser079', 'scrypt:32768:8:1$AosoX2pkAqoX7Kkz$e6d3e102b16671cc907504720481317c528b90c49bb95c9500e51f72134a5e365ca04a0884522c9e614841b7c7b69f8b05d607b19f14ab97395fccc99d6cb622', 'user079@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user080', 'testuser080', 'scrypt:32768:8:1$ev16buG4QWPo4TsS$af739c4a5f34febe6269532d97354f5bb6c7261577430273ab78483dffcaa09c41e0c097b2452c2543955bf067811b594dd0bac3ae21a5e2d7fda4917d4b5bfd', 'user080@example.com', NULL, NULL, '2025-06-05', 'enable'),
('user081', 'JJun504', 'scrypt:32768:8:1$v31tyqor0XGkegTT$1b0e9df0a2ec50a1aff102f6b0aeb2732e8b62df750cd40f171de906d246067a9c5197cf9efde7fd6da45e249789586b34b1844f1d4722dede93d6d740ce525e', 'wtgoh1002@gmail.com', NULL, NULL, '2025-06-06', 'enable'),
('user082', 'JJun504', 'scrypt:32768:8:1$XGDexyo7SchPxdt0$bce50b03b93cb65eb6b6113f0a4b50f1d2e669e67ba327e4f84070a20b597f6566489b76b00ddc6b23a1e1716fc177a19345d4d883a34fd6e706e81f27a7ae82', 'wtgoh1003@gmail.com', '', '/avatar/user082/1749208306_FJnqzyvUcAELTb_.jpeg', '2025-06-06', 'enable'),
('user083', 'Gwt', 'scrypt:32768:8:1$4MMrTBIlC6C8AQyW$8b9c2f89ef244f53e248eb5819c395296a8fe257d163bd203b537de41a1d68967a8d74221691283a9c181b7a9e459e8a49cf05c83937cf11aba4523a5d0a2e4a', 'wtgoh1004@gmail.com', '', '/avatar/user083/1749391642_Screenshot 2024-08-14 163159.png', '2025-06-08', 'enable'),
('user084', 'Gwt', 'scrypt:32768:8:1$SCF7ha73qpGmHblH$9c33dd7aaa0a143b01b75513e3d801c3038dc4ff3effcbc7c96307fb0a1690c6865d253af86538a712d67e82af90487a5781ba0c53e3691403acf53f06cafd99', 'wtgoh0609@gmail.com', '', NULL, '2025-06-08', 'enable');

-- --------------------------------------------------------

--
-- 表的结构 `user_model`
--

CREATE TABLE `user_model` (
  `id` int(11) NOT NULL,
  `user_id` varchar(10) NOT NULL,
  `model_id` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- 转存表中的数据 `user_model`
--

INSERT INTO `user_model` (`id`, `user_id`, `model_id`) VALUES
(10, 'user001', 'yumi001'),
(11, 'user001', 'yumi002'),
(15, 'user001', 'yumi003'),
(16, 'user001', 'yumi004'),
(26, 'user001', 'yumi005'),
(147, 'user083', 'yumi007'),
(149, 'user001', 'yumi006'),
(150, 'user083', 'yumi010'),
(151, 'user001', 'yumi011');

--
-- 转储表的索引
--

--
-- 表的索引 `admin`
--
ALTER TABLE `admin`
  ADD PRIMARY KEY (`admin_id`);

--
-- 表的索引 `config`
--
ALTER TABLE `config`
  ADD PRIMARY KEY (`config_id`),
  ADD KEY `model_id` (`model_id`);

--
-- 表的索引 `model`
--
ALTER TABLE `model`
  ADD PRIMARY KEY (`model_id`);

--
-- 表的索引 `scene`
--
ALTER TABLE `scene`
  ADD PRIMARY KEY (`scene_id`),
  ADD KEY `user_id` (`user_id`);

--
-- 表的索引 `schedule`
--
ALTER TABLE `schedule`
  ADD PRIMARY KEY (`schedule_id`),
  ADD KEY `user_id` (`user_id`),
  ADD KEY `model_id` (`model_id`);

--
-- 表的索引 `smart_home`
--
ALTER TABLE `smart_home`
  ADD PRIMARY KEY (`smart_home_id`),
  ADD KEY `model_id` (`model_id`);

--
-- 表的索引 `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`user_id`);

--
-- 表的索引 `user_model`
--
ALTER TABLE `user_model`
  ADD PRIMARY KEY (`id`),
  ADD KEY `user_id` (`user_id`);

--
-- 在导出的表使用AUTO_INCREMENT
--

--
-- 使用表AUTO_INCREMENT `admin`
--
ALTER TABLE `admin`
  MODIFY `admin_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=2;

--
-- 使用表AUTO_INCREMENT `config`
--
ALTER TABLE `config`
  MODIFY `config_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- 使用表AUTO_INCREMENT `model`
--
ALTER TABLE `model`
  MODIFY `model_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=101;

--
-- 使用表AUTO_INCREMENT `scene`
--
ALTER TABLE `scene`
  MODIFY `scene_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- 使用表AUTO_INCREMENT `schedule`
--
ALTER TABLE `schedule`
  MODIFY `schedule_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- 使用表AUTO_INCREMENT `smart_home`
--
ALTER TABLE `smart_home`
  MODIFY `smart_home_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- 使用表AUTO_INCREMENT `user_model`
--
ALTER TABLE `user_model`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=152;

--
-- 限制导出的表
--

--
-- 限制表 `config`
--
ALTER TABLE `config`
  ADD CONSTRAINT `config_ibfk_1` FOREIGN KEY (`model_id`) REFERENCES `model` (`model_id`);

--
-- 限制表 `scene`
--
ALTER TABLE `scene`
  ADD CONSTRAINT `scene_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`);

--
-- 限制表 `schedule`
--
ALTER TABLE `schedule`
  ADD CONSTRAINT `schedule_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`),
  ADD CONSTRAINT `schedule_ibfk_2` FOREIGN KEY (`model_id`) REFERENCES `model` (`model_id`);

--
-- 限制表 `smart_home`
--
ALTER TABLE `smart_home`
  ADD CONSTRAINT `smart_home_ibfk_1` FOREIGN KEY (`model_id`) REFERENCES `model` (`model_id`);

--
-- 限制表 `user_model`
--
ALTER TABLE `user_model`
  ADD CONSTRAINT `user_model_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
