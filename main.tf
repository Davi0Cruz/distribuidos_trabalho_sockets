terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
      version = "5.83.1"
    }
  }
}

provider "aws" {
    region = "us-east-1"
}

data "aws_availability_zones" "available" {
    state = "available"
}

resource "aws_vpc" "vpc_multicast" {
    cidr_block = "10.0.0.0/16"
    enable_dns_support = true
    enable_dns_hostnames = true
}

resource "aws_subnet" "subnet_multicast" {
    vpc_id     = aws_vpc.vpc_multicast.id
    map_public_ip_on_launch = true
    cidr_block = "10.0.0.0/24"
    availability_zone = data.aws_availability_zones.available.names[0]
}

resource "aws_internet_gateway" "gateway" {
    vpc_id = aws_vpc.vpc_multicast.id
}

resource "aws_route_table" "route_table" {
    vpc_id = aws_vpc.vpc_multicast.id

    route {
        cidr_block = "0.0.0.0/0"
        gateway_id = aws_internet_gateway.gateway.id
    }
}


resource "aws_route_table_association" "route_table_association" {
    subnet_id      = aws_subnet.subnet_multicast.id
    route_table_id = aws_route_table.route_table.id
}

resource "aws_security_group" "multicast" {
    name       = "multicast"
    description = "Allow multicast traffic"
    vpc_id = aws_vpc.vpc_multicast.id
    tags = {
      Name = "multicast"
    }
}

resource "aws_vpc_security_group_ingress_rule" "ingress_multicast" {
    security_group_id = aws_security_group.multicast.id
    ip_protocol = "-1"
    cidr_ipv4 = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "egress_multicast" {
    security_group_id = aws_security_group.multicast.id
    ip_protocol = "-1"
    cidr_ipv4 = "0.0.0.0/0"
}


resource "aws_network_interface" "gateway" {
    subnet_id   = aws_subnet.subnet_multicast.id
    security_groups = [aws_security_group.multicast.id]
    tags = {
      Name = "ni_gateway"
    }
}

resource "aws_network_interface" "devices" {
    subnet_id   = aws_subnet.subnet_multicast.id
    security_groups = [aws_security_group.multicast.id]
    tags = {
      Name = "ni_devices"
    }
}

resource "aws_ec2_transit_gateway" "multicast" {
    description = "Multicast Transit Gateway"
    multicast_support = "enable"
    tags = {
        Name = "multicast"
    }
  
}

resource "aws_ec2_transit_gateway_multicast_domain" "transit_gateway_multicast_domain" {
    transit_gateway_id = aws_ec2_transit_gateway.multicast.id

    igmpv2_support = "enable"

    tags = {
        Name = "multicast"
    }
}

resource "aws_ec2_transit_gateway_vpc_attachment" "multicast_attachment" {
    subnet_ids = [aws_subnet.subnet_multicast.id]
    transit_gateway_id = aws_ec2_transit_gateway.multicast.id
    vpc_id = aws_vpc.vpc_multicast.id
}

resource "aws_ec2_transit_gateway_multicast_domain_association" "association_multicast" {
    subnet_id = aws_subnet.subnet_multicast.id
    transit_gateway_attachment_id = aws_ec2_transit_gateway_vpc_attachment.multicast_attachment.id
    transit_gateway_multicast_domain_id = aws_ec2_transit_gateway_multicast_domain.transit_gateway_multicast_domain.id
}


resource "aws_instance" "gateway" {
    ami           = "ami-05576a079321f21f8"
    instance_type = "t2.micro"
    key_name = "multicast"
    network_interface {
        network_interface_id = aws_network_interface.gateway.id
        device_index = 0
    }
    tags = {
      Name = "gateway"
    }
}

resource "aws_instance" "devices" {
    ami           = "ami-05576a079321f21f8"
    instance_type = "t2.micro"
    key_name = "multicast"
    network_interface {
        network_interface_id = aws_network_interface.devices.id
        device_index = 0
    }
    tags = {
      Name = "devices"
    }
}

resource "time_sleep" "wait_30_seconds" {
    depends_on = [aws_instance.gateway, aws_instance.devices, aws_ec2_transit_gateway_multicast_domain_association.association_multicast]
    create_duration = "30s"
  
}

resource "aws_ec2_transit_gateway_multicast_group_member" "gateway" {
    depends_on = [ time_sleep.wait_30_seconds ]
    group_ip_address = "224.0.0.1"
    network_interface_id = aws_network_interface.gateway.id
    transit_gateway_multicast_domain_id = aws_ec2_transit_gateway_multicast_domain.transit_gateway_multicast_domain.id
}

resource "aws_ec2_transit_gateway_multicast_group_member" "devices" {
    depends_on = [ time_sleep.wait_30_seconds ]
    group_ip_address = "224.0.0.1"
    network_interface_id = aws_network_interface.devices.id
    transit_gateway_multicast_domain_id = aws_ec2_transit_gateway_multicast_domain.transit_gateway_multicast_domain.id
}


output "ip_gateway" {
    value = aws_instance.gateway.public_ip
}

output "ip_devices" {
    value = aws_instance.devices.public_ip
}