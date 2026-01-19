# --- Apptio API Settings ---
LOGIN_URL = "https://frontdoor-in.apptio.com/service/apikeylogin"
ENV_ID = "a0a4ceef-47a3-51a5-c082-12db8c6f0281"

# --- GCP Settings ---
PROJECT_ID = "hbl-gcp-prod-finops-prj-spk-d1" 
REGION_ID = "asia-south1"
KEY_ACCESS_ID = "finops-agent-apptio-public-key"
KEY_SECRET_ID = "finops-agent-apptio-private-key"
SECRET_VERSION = "latest"
BUCKET_NAME = "finops-apptio-recommendations"

# --- Cloud Provider Recommendations Mappings ---
PROVIDERS = {
    "aws": {
        "folder": "aws",
        "resources": [
            {
                "name": "ec2",
                "url": "https://api-in.cloudability.com/v3/rightsizing/aws/recommendations/ec2?vendorAccountIds=&basis=on-demand&filters=recommendations.defaultsOrder%3D%3D1&limit=25&maxRecsPerResource=1&offset=0&product=ec2&sort=-recommendations.savings&duration=thirty-day&viewId=0",
                "file": "aws_ec2_recommendations"
            },
            {
                "name": "ec2-asg",
                "url": "https://api-in.cloudability.com/v3/rightsizing/aws/recommendations/ec2-asg?basis=on-demand&duration=thirty-day&filters=recommendations.defaultsOrder%3D%3D1&limit=25&maxRecsPerResource=1&offset=0&product=ec2-asg&sort=-recommendations.savings&vendorAccountIds=&viewId=0",
                "file": "aws_ec2_asg_recommendations"
            },
            {
                "name": "ebs",
                "url": "https://api-in.cloudability.com/v3/rightsizing/aws/recommendations/ebs?vendorAccountIds=&basis=on-demand&duration=thirty-day&limit=25&maxRecsPerResource=1&offset=0&sort=-recommendations.savings&viewId=0&filters=recommendations.rank%3D%3D1&product=ebs",
                "file": "aws_ebs_recommendations"
            },
            {
                "name": "s3",
                "url": "https://api-in.cloudability.com/v3/rightsizing/aws/recommendations/s3?vendorAccountIds=&basis=on-demand&duration=thirty-day&limit=25&maxRecsPerResource=1&offset=0&sort=-recommendations.savings&viewId=0&filters=recommendations.rank%3D%3D1&product=s3",
                "file": "aws_s3_recommendations"
            },
            {
                "name": "rds",
                "url": "https://api-in.cloudability.com/v3/rightsizing/aws/recommendations/rds?vendorAccountIds=&basis=on-demand&duration=thirty-day&limit=25&maxRecsPerResource=1&offset=0&viewId=0&filters=recommendations.preferenceOrder%3D%3D1&product=rds&sort=-topSavings",
                "file": "aws_rds_recommendations"
            },
            {
                "name": "redshift-clusters-underutilized",
                "url": "https://api-in.cloudability.com/v3/rightsizing/aws/underutilized/redshift?filters=&vendorAccountIds=&duration=thirty-day&limit=25&offset=0&viewId=0&basis=cost&product=redshift&sort=-priority",
                "file": "aws_redshift_recommendations"
            }
        ]
    },
    "azure": {
        "folder": "azure",
        "resources": [
            {
                "name": "compute",
                "url": "https://api-in.cloudability.com/v3/rightsizing/azure/recommendations/compute?limit=25&offset=0&duration=thirty-day&maxRecsPerResource=1&sort=-recommendations.savings&viewID=0",
                "file": "azure_compute_recommendations"
            }, 
            {
                "name": "sql",
                "url": "https://api-in.cloudability.com/v3/rightsizing/azure/recommendations/sql?limit=25&offset=0&duration=thirty-day&maxRecsPerResource=1&sort=-recommendations.savings&viewID=0",
                "file": "azure_sql_recommendations"
            }, 
            {
                "name": "disk",
                "url": "https://api-in.cloudability.com/v3/rightsizing/azure/recommendations/disk?limit=25&offset=0&duration=thirty-day&maxRecsPerResource=1&sort=-recommendations.savings&viewID=0",
                "file": "azure_disk_recommendations"
            }
        ]   
    },
    "gcp": {
        "folder": "gcp",
        "resources": [
            {
                "name": "compute", 
                "url": "https://api-in.cloudability.com/v3/rightsizing/gcp/recommendations/compute?vendorAccountIds=&basis=on-demand&duration=thirty-day&limit=25&maxRecsPerResource=1&offset=0&sort=-recommendations.savings&viewId=0&filters=recommendations.preferenceOrder%3D%3D1&product=gcp-compute",
                "file": "gcp_compute_recommendations"
            }, 
            {
                "name": "disk", 
                "url": "https://api-in.cloudability.com/v3/rightsizing/gcp/recommendations/disk?vendorAccountIds=&basis=on-demand&duration=thirty-day&limit=25&maxRecsPerResource=1&offset=0&sort=-recommendations.savings&viewId=0&filters=recommendations.preferenceOrder%3D%3D1&product=gcp-disk",
                "file": "gcp_disk_recommendations"
            }
        ]
    }, 
    "container_recommendations": {
        "folder": "", 
        "resources": [
            {
                "name": "container_recommendations",
                "url": "https://api-in.cloudability.com/v3/rightsizing/containers/recommendations/workloads?limit=25&offset=0&maxRecsPerResource=1&duration=thirty-day&basis=on-demand&viewid=0",
                "file": "container_recommendations"
            }
        ]
    }
}